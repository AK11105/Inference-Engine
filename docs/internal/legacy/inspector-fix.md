# Inspector Overhaul

## Problem Summary

The current inspector is a single monolithic subprocess script that fails completely on any exception. It uses one loading strategy (pickle) for all artifact types, interprets metadata with hardcoded rules, and returns `returncode != 0` on failure — causing the CLI to `sys.exit(1)` and discard everything learned so far. The result is a brittle first step that poisons the entire deploy pipeline.

---

## Design Principles

1. **The subprocess always exits 0 and always prints valid JSON.** `returncode != 0` is reserved for "Python couldn't start" or "file not found before inspection began." Everything else is partial data.
2. **Extract facts, don't interpret them.** The extractor's job is to read structure. Meaning is assigned by the LLM interpretation stage.
3. **Each extraction layer catches its own failures.** A crash in deep metadata extraction does not discard file-system facts already collected.
4. **Uncertainty is explicit.** Every metadata field carries a provenance. The LLM knows what was measured vs guessed vs unknown.
5. **The LLM is part of inspection, not downstream of it.** For ambiguous artifacts, LLM interpretation runs before codegen, not after a failed attempt.

---

## Architecture

```
User runs: inference-engine deploy ./model.pkl

┌─────────────────────────────────────────────────────┐
│  Stage 1: Rule-based extraction (subprocess sandbox) │
│                                                      │
│  Layer 0: filesystem facts      → always succeeds   │
│  Layer 1: format identification → extension + magic  │
│  Layer 2: safe structural read  → format-specific   │
│  Layer 3: deep attribute scan   → best-effort       │
│                                                      │
│  Output: raw_facts + inspection_errors + confidence  │
└─────────────────────────────────────────────────────┘
                        │
          ┌─────────────┴──────────────┐
          │ confidence == high          │ confidence < high
          │ framework known             │ OR framework == generic
          ▼                             ▼
   skip LLM interpretation     ┌───────────────────────┐
          │                    │  Stage 2: LLM          │
          │                    │  interpretation call   │
          │                    │                        │
          │                    │  input: raw_facts,     │
          │                    │  errors, sample_input, │
          │                    │  --framework hint      │
          │                    │                        │
          │                    │  output: enriched      │
          │                    │  metadata + READY      │
          │                    │  or + question         │
          │                    └───────────────────────┘
          │                             │
          │                    ┌────────┴────────┐
          │                    │ READY           │ question
          │                    │                 ▼
          │                    │         ask user (max 2)
          │                    │         patch metadata
          │                    └────────┐
          └────────────────────────────┘
                        │
                        ▼
              codegen (generate)
                        │
                  validate + fix loop
                        │
                      write
```

---

## Stage 1: Layered Extraction

### Format Detection

Before loading anything, identify the format from extension and magic bytes:

| Extension | Format | Extractor |
|---|---|---|
| `.pkl`, `.pickle` | Pickle | `PickleExtractor` |
| `.joblib` | Joblib | `PickleExtractor` (via joblib) |
| `.pt`, `.pth` | PyTorch | `TorchExtractor` |
| `.onnx` | ONNX | `OnnxExtractor` |
| `.safetensors` | Safetensors | `SafetensorsExtractor` |
| directory | HuggingFace / TF SavedModel | `DirectoryExtractor` |
| unknown | fallback | `GenericExtractor` |

Magic byte check as fallback when extension is missing or wrong (e.g. `.bin` files).

### Layer 0 — Filesystem Facts (always succeeds)

```python
raw_facts = {
    "artifact_path": path,
    "artifact_size_mb": round(os.path.getsize(path) / (1024**2), 2),
    "extension": os.path.splitext(path)[1].lower(),
    "is_directory": os.path.isdir(path),
    "errors": [],
}
```

### Layer 1 — Format Identification

```python
try:
    raw_facts["format"] = detect_format(path)   # extension + magic bytes
    raw_facts["format_confidence"] = "known" | "inferred"
except Exception as e:
    raw_facts["format"] = "unknown"
    raw_facts["errors"].append({"layer": "format", "error": str(e)})
```

### Layer 2 — Safe Structural Read (format-specific)

Each extractor reads structure without executing model code. Crashes are caught and appended to `errors`.

**PickleExtractor**
```python
# try joblib first, fall back to pickle
obj = joblib.load(path)  # or pickle.load

raw_facts["class_name"] = type(obj).__name__
raw_facts["module"] = type(obj).__module__
raw_facts["attributes"] = list(vars(obj).keys())   # full attribute map for LLM
raw_facts["has_steps"] = hasattr(obj, "steps")
raw_facts["has_predict"] = hasattr(obj, "predict")
raw_facts["has_predict_proba"] = hasattr(obj, "predict_proba")
```

**TorchExtractor**
```python
# weights_only=True prevents arbitrary code execution
data = torch.load(path, map_location="cpu", weights_only=True)

if isinstance(data, dict):
    raw_facts["load_format"] = "state_dict"
    raw_facts["state_dict_keys"] = list(data.keys())[:30]  # first 30 layer names
    raw_facts["param_count"] = sum(v.numel() for v in data.values() if hasattr(v, "numel"))
else:
    raw_facts["load_format"] = "full_model"
    raw_facts["class_name"] = type(data).__name__
    raw_facts["layer_names"] = [name for name, _ in data.named_children()]
```

State dict key names like `encoder.layer.0.attention.self.query.weight` are highly informative for the LLM — they reveal architecture without loading the model.

**OnnxExtractor**
```python
model = onnx.load(path)
raw_facts["opset"] = model.opset_import[0].version
raw_facts["op_types"] = list({n.op_type for n in model.graph.node})  # architecture signal
raw_facts["inputs"] = [
    {
        "name": i.name,
        "shape": [
            d.dim_param if d.dim_param else d.dim_value   # preserve dynamic axes as strings
            for d in i.type.tensor_type.shape.dim
        ],
        "dtype": i.type.tensor_type.elem_type,
    }
    for i in model.graph.input
]
raw_facts["outputs"] = [...]  # same pattern
```

Note: `dim_param` captures dynamic axes (e.g. `"batch_size"`, `"sequence_length"`) instead of collapsing them to `0`.

**SafetensorsExtractor**
```python
# reads header only — no weight data loaded into memory
with safetensors.safe_open(path, framework="pt") as f:
    raw_facts["tensor_keys"] = list(f.keys())[:30]
    raw_facts["metadata"] = f.metadata()   # often contains model_type
    raw_facts["tensor_shapes"] = {k: list(f.get_slice(k).get_shape()) for k in list(f.keys())[:10]}
```

**DirectoryExtractor**
```python
files = os.listdir(path)
raw_facts["directory_files"] = files

if "config.json" in files:
    with open(os.path.join(path, "config.json")) as f:
        cfg = json.load(f)
    raw_facts["hf_config"] = {
        "model_type": cfg.get("model_type"),
        "architectures": cfg.get("architectures"),
        "hidden_size": cfg.get("hidden_size"),
        "num_labels": cfg.get("num_labels"),
        "num_hidden_layers": cfg.get("num_hidden_layers"),
    }

if "tokenizer_config.json" in files:
    with open(os.path.join(path, "tokenizer_config.json")) as f:
        raw_facts["tokenizer_class"] = json.load(f).get("tokenizer_class")

if "saved_model.pb" in files:
    raw_facts["format"] = "tf_savedmodel"

if "adapter_config.json" in files:
    raw_facts["is_peft_adapter"] = True
```

No model loading at all. Pure JSON reads.

### Layer 3 — Deep Attribute Scan (best-effort, sklearn/xgb/lgb/catboost)

Only runs for pickle-loaded objects where Layer 2 succeeded. Extracts sklearn-style attributes:

```python
try:
    if hasattr(obj, "steps"):
        raw_facts["pipeline_steps"] = [type(s).__name__ for _, s in obj.steps]
    if hasattr(obj, "n_features_in_"):
        raw_facts["n_features_in"] = int(obj.n_features_in_)
    if hasattr(obj, "classes_"):
        raw_facts["classes"] = obj.classes_.tolist()
    if hasattr(obj, "n_estimators"):
        raw_facts["n_estimators"] = obj.n_estimators
    if hasattr(obj, "objective"):
        raw_facts["objective"] = str(obj.objective)
except Exception as e:
    raw_facts["errors"].append({"layer": "deep", "error": str(e)})
    # continue — don't stop
```

### Confidence Derivation

Computed from what was actually extracted, not assumed:

```python
def _compute_confidence(raw_facts: dict) -> str:
    known = sum(1 for k, v in raw_facts.items()
                if k not in ("errors", "artifact_path") and v not in (None, "unknown", []))
    total = len(raw_facts) - 2  # exclude errors and path
    ratio = known / total if total else 0

    if raw_facts.get("errors"):
        return "low" if len(raw_facts["errors"]) > 1 else "medium"
    if ratio > 0.7:
        return "high"
    if ratio > 0.4:
        return "medium"
    return "low"
```

---

## ArtifactMetadata

Fields become explicit about what was learned vs unknown:

```python
@dataclass
class ArtifactMetadata:
    # always present
    artifact_path: str
    artifact_size_mb: float
    extension: str
    confidence: str                        # "high" | "medium" | "low"
    inspection_errors: list[dict]          # [{layer, error}] — for LLM and --verbose

    # extracted (None = unknown, not missing)
    framework: str | None
    class_name: str | None
    load_format: str | None                # "state_dict" | "full_model" | "joblib" | etc
    class_hierarchy: list | None
    input_hint: str | None
    output_hint: str | None
    feature_count: int | None
    class_labels: list | None

    # raw facts passed to LLM interpretation
    raw_facts: dict = field(default_factory=dict)
```

`raw_facts` is the full uninterpreted dict from the subprocess — passed directly to the LLM interpretation prompt so it has all available evidence.

---

## Stage 2: LLM Interpretation

Fires when `confidence < high` or `framework is None`. This is a separate LLM call before codegen.

### System prompt

```
You are analyzing a machine learning artifact to determine how to load and run it.
You receive raw structural facts extracted from the artifact file.
Your job is to interpret these facts and fill in missing information.

Return a JSON object with:
- framework: one of sklearn, pytorch, transformers, xgboost, lightgbm, catboost,
             onnx, sentence_transformers, tf_savedmodel, generic
- load_format: how to load the artifact (e.g. "joblib", "torch.load+state_dict",
               "from_pretrained", "onnxruntime.InferenceSession")
- input_hint: what predict() receives (be specific about shape/type)
- output_hint: what predict() returns
- confidence: your confidence in this interpretation ("high" | "medium" | "low")
- question: if confidence is not high, one short specific question to ask the user
            that would resolve the most important uncertainty. null if not needed.
- question_field: which field the question resolves (e.g. "load_format", "input_hint")

Only ask a question if it would materially change how load() or predict() is written.
If you have enough to generate correct code, set question to null.
```

### User prompt construction

```python
def _build_interpretation_prompt(raw_facts: dict, sample_input: Any, framework_hint: str | None) -> str:
    lines = ["Raw facts extracted from artifact:"]
    lines.append(json.dumps(raw_facts, indent=2))

    if sample_input is not None:
        lines.append(f"\nSample input provided by user: {sample_input!r}")
        lines.append("Use this to infer input type and shape if input_hint is unclear.")

    if framework_hint:
        lines.append(f"\nUser specified --framework {framework_hint}. Trust this for framework detection.")

    if raw_facts.get("errors"):
        lines.append(f"\nInspection errors (some layers failed): {raw_facts['errors']}")
        lines.append("Account for these gaps in your interpretation.")

    lines.append("\nReturn JSON only.")
    return "\n".join(lines)
```

### Clarifying question flow

```python
def _maybe_clarify(meta: ArtifactMetadata, answers: DeployAnswers) -> ArtifactMetadata:
    interp = llm_interpret(meta.raw_facts, answers.sample_input, answers.framework_hint)
    meta = _patch_metadata(meta, interp)

    if interp.get("question") and _is_interactive():
        for _ in range(2):   # max 2 questions
            answer = _ask_user(interp["question"])
            meta.raw_facts[interp["question_field"]] = answer
            interp = llm_interpret(meta.raw_facts, answers.sample_input, answers.framework_hint)
            meta = _patch_metadata(meta, interp)
            if not interp.get("question"):
                break

    return meta
```

Non-interactive (CI) mode skips questions and proceeds with what was inferred.

---

## --framework Flag

Optional hint that short-circuits framework detection. Does not skip the rest of inspection.

```bash
inference-engine deploy ./model.pt --framework pytorch
inference-engine deploy ./model.pkl --framework xgboost
```

Effect:
- Sets `raw_facts["framework_hint"]` before extraction
- Passed to LLM interpretation prompt as trusted input
- If `confidence` would otherwise be `low` but framework is now known, re-evaluate — may skip clarify step entirely
- Does not suppress inspection errors or skip structural extraction

---

## sample_input in Generation Prompt

Currently `sample_input` is only used for validation. It must also feed into the generation prompt:

```python
# in _build_user_prompt (agent.py)
if sample_input is not None:
    lines.append(f"\nSample input: {sample_input!r}")
    lines.append("predict() must handle this exact input type.")
```

This is the single cheapest improvement — `"this movie was great"` tells the LLM more about input handling than any inferred hint.

---

## Fix Loop Enrichment

The fix prompt currently sends only the traceback and the broken code. It must also include:

```python
user_prompt = (
    f"The following code failed:\n\n```\n{error}\n```\n\n"
    f"Code:\n\n```python\n{previous_code}\n```\n\n"
    f"Artifact metadata:\n{json.dumps(meta_summary)}\n\n"   # ← add this
    f"Sample input used during validation: {sample_input!r}\n\n"  # ← add this
    f"Fix load() and predict(). Return only the two corrected method bodies."
)
```

Without this, the LLM is fixing blind — it doesn't know what input caused the failure.

---

## CLI Output Changes

### Current (bad)
```
Error: Inspection failed:
Traceback (most recent call last):
  ...
ModuleNotFoundError: No module named 'xgboost'
```
→ `sys.exit(1)`, user starts over.

### New (graceful)
```
Inspector
  Format       pickle / XGBClassifier
  Size         2.1 MB
  Framework    unknown  ⚠ (xgboost not installed in inspection env)
  Attributes   [n_estimators, objective, feature_names_in_, ...]

Confidence: low — proceeding with LLM interpretation.

? What framework is this model from?
  Detected class: XGBClassifier — is this an XGBoost model? (Y/n) >
```

Rules:
- Never print a raw traceback to the user unless `--verbose` is passed
- Inspection errors go into `meta.inspection_errors`, shown only with `--verbose`
- Always continue past inspection failures — partial metadata is better than nothing
- Confidence level is always shown before codegen so the user knows what the LLM is working with

---

## File Changes

| File | Change |
|---|---|
| `app/cli/core/inspector.py` | Replace monolithic script with layered extractors per format; always exit 0; add `raw_facts`, `confidence`, `inspection_errors` to `ArtifactMetadata` |
| `app/cli/core/agent.py` | Add `interpret()` function for LLM interpretation stage; enrich `fix()` prompt with metadata + sample_input; add `sample_input` to `generate()` prompt |
| `app/cli/core/prompts.py` | Add `--framework` to `DeployAnswers`; add clarifying question prompt renderer |
| `app/cli/commands/deploy.py` | Add `--framework` flag; insert interpretation + clarify step between inspection and codegen; replace `sys.exit(1)` on inspection failure with graceful continuation |
| `app/cli/__main__.py` | Expose `--framework` on the CLI |

---

## Summary

The inspector becomes a **fact collector**, not an interpreter. It runs in a subprocess sandbox, uses format-specific extractors, catches failures per-layer, and always returns partial JSON. The LLM interpretation stage assigns meaning to those facts — and asks the user one targeted question if it can't. The `--framework` flag and `sample_input` both feed into interpretation as trusted signals. The fix loop gets the same context. The CLI never exits on an inspection failure — it degrades gracefully and keeps the user in the flow.
