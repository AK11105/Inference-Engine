# Inspector Overhaul — Design Reference
*Combines: `inspector-fix.md` (v1 implementation spec) and `inspector-fix-new-ideas.md` (v2 architecture extensions)*
*Last updated: 2026-06-22*

---

## Problem Summary

The current inspector is a single monolithic subprocess script that:

- Fails completely on any exception — returns `returncode != 0`, causing `sys.exit(1)` and discarding everything learned
- Uses one loading strategy (`pickle.load`) for all artifact types
- Interprets metadata with hardcoded rules
- Tightly couples framework detection to artifact loading
- Makes large artifacts (multi-GB models) impractical to inspect
- Mixes metadata extraction and interpretation in the same stage
- Has no caching — repeated deploy attempts repeatedly inspect the same artifact

The result is a brittle first step that poisons the entire deploy pipeline and scales poorly as model size and framework diversity increase.

---

## Design Principles

1. **The subprocess always exits 0 and always prints valid JSON.** `returncode != 0` is reserved for "Python couldn't start" or "file not found before inspection began." Everything else is partial data.
2. **Inspection is fact collection, not interpretation.** The inspector extracts measurable facts. It does not decide how to deploy, what framework semantics mean, or how `predict()` should behave. Interpretation belongs to the LLM stage.
3. **Deployment must not depend on model loading.** Large models should be deployable through metadata and deployment specifications alone.
4. **Each extraction layer catches its own failures.** A crash in deep metadata extraction does not discard filesystem facts already collected.
5. **Partial knowledge is valuable.** Inspection should never fail the deploy flow. Any information successfully extracted remains useful.
6. **Uncertainty is explicit.** Every metadata field carries provenance. Confidence is attached to every interpretation stage.
7. **Scale-aware inspection.** Inspection behavior changes based on artifact size and format. The system does not deserialize large artifacts merely to identify them.
8. **Artifact introspection is an onboarding accelerator, not the primary deployment mechanism.** The primary deployment contract is a deployment package.

---

## High-Level Architecture

```text
User runs: inference-engine deploy ./model.pkl

┌─────────────────────────────────────────────────────┐
│  Stage 1: Rule-based extraction (subprocess sandbox) │
│                                                      │
│  Layer 0: filesystem facts      → always succeeds   │
│  Layer 1: format identification → extension + magic  │
│  Layer 2: safe structural read  → format-specific   │
│  Layer 3: deep attribute scan   → best-effort       │
│                                                      │
│  Output: RawFacts (with per-field provenance)        │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  Stage 1.5: DeploymentSpec Builder                   │
│                                                      │
│  build_deployment_spec(raw_facts)                    │
│  → DeploymentSpecCandidate                           │
│  → deployment_readiness derived from rules           │
└─────────────────────────────────────────────────────┘
                        │
          ┌─────────────┴──────────────────┐
          │ readiness == ready              │ readiness != ready
          ▼                                 ▼
   skip LLM interpretation         ┌───────────────────────┐
          │                        │  Stage 2: LLM          │
          │                        │  interpretation call   │
          │                        │                        │
          │                        │  input: raw_facts,     │
          │                        │  errors, sample_input, │
          │                        │  --framework hint,     │
          │                        │  spec candidate        │
          │                        │                        │
          │                        │  output: enriched      │
          │                        │  DeploymentSpec +      │
          │                        │  READY or question     │
          │                        └───────────────────────┘
          │                                 │
          │                        ┌────────┴────────┐
          │                        │ READY           │ question
          │                        │                 ▼
          │                        │         ask user (max 2)
          │                        │         patch raw_facts
          │                        └────────┐
          └────────────────────────────────┘
                        │
                        ▼
              DeploymentSpec
                        │
                  codegen (generate)
                        │
                  validate + fix loop
                        │
                      write
```

Full deployment lifecycle (long-term):

```text
Artifact
    ↓
Inspector → RawFacts (with per-field provenance)
    ↓
DeploymentSpec Builder → DeploymentSpecCandidate
    ↓
LLM Interpretation (conditional on deployment_readiness)
    ↓
DeploymentSpec
    ↓
Code Generation
    ↓
Validation
    ↓
Deploy
```

---

## Deployment Package Contract

The canonical deployment target is a deployment package, not artifact inspection:

```bash
inference-engine init model.pkl   # generates deploy.yaml + package from artifact
inference-engine deploy my-model/ # reads deploy.yaml, never re-inspects artifact
```

Package structure:

```text
my-model/
├── deploy.yaml
├── artifacts/
├── src/
│   └── handler.py
├── requirements.txt
```

`init` creates `deploy.yaml` from the inspection result. `deploy` reads `deploy.yaml` and does not re-inspect the artifact unless `--refresh-inspection` is explicitly passed. This is the primary performance and reliability win from the v2 design — repeated `deploy` calls are cheap and deterministic.

Artifact inspection (`inference-engine init`) is the onboarding accelerator. Production deployment depends on the `DeploymentSpec` in `deploy.yaml`, not on re-loading the artifact.

---

## Field-Level Provenance

Every interpreted field carries its source and confidence. Raw measured values (filesystem, extractor) are unambiguous — only derived or inferred fields need provenance.

```python
@dataclass
class FieldValue:
    value: Any
    source: Literal["filesystem", "extractor", "llm", "user", "default"]
    confidence: str  # "high" | "medium" | "low"
```

Example `RawFacts` output:

```json
{
  "framework": {
    "value": "xgboost",
    "source": "llm",
    "confidence": "medium"
  },
  "load_format": {
    "value": "joblib",
    "source": "extractor",
    "confidence": "high"
  },
  "input_hint": {
    "value": "numpy array, shape (n, 20)",
    "source": "user",
    "confidence": "high"
  }
}
```

Source hierarchy (highest wins on conflict):

```text
user > extractor > llm > default
```

This makes the explain mode output precise ("framework was inferred by LLM at medium confidence") and gives the fix loop concrete context about what is known vs guessed.

---

## Stage 1 — Layered Rule-Based Extraction

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

---

### Layer 0 — Filesystem Facts (always succeeds)

```python
raw_facts = {
    "artifact_path": path,
    "artifact_size_mb": round(os.path.getsize(path) / (1024**2), 2),
    "artifact_hash": sha256(path),      # cache key
    "extension": os.path.splitext(path)[1].lower(),
    "is_directory": os.path.isdir(path),
    "errors": [],
}
```

---

### Layer 1 — Format Identification

```python
try:
    raw_facts["format"] = detect_format(path)   # extension + magic bytes
    raw_facts["format_confidence"] = "known" | "inferred"
except Exception as e:
    raw_facts["format"] = "unknown"
    raw_facts["errors"].append({"layer": "format", "error": str(e)})
```

---

### Layer 2 — Safe Structural Read (format-specific)

Each extractor reads structure without executing model code. Crashes are caught and appended to `errors`.

**Pickle safety gate**

Pickle deserialization is only permitted when all three conditions are met:

1. `inspection_mode == "loaded"` (artifact ≤ 100 MB)
2. User passed `--allow-load` or confirmed the prompt in interactive mode
3. `safety.deserialization_risk` has been shown to the user

```python
if not _pickle_load_permitted(raw_facts, answers):
    raw_facts["errors"].append({
        "layer": "structural",
        "error": "pickle deserialization skipped — use --allow-load to permit"
    })
    return raw_facts
```

In non-interactive (`--yes`) mode, `--allow-load` must be explicit. Pickle artifacts without `--allow-load` get metadata-only treatment regardless of size.

**PickleExtractor** (runs only after safety gate)
```python
obj = joblib.load(path)  # fallback: pickle.load

raw_facts["class_name"] = FieldValue(type(obj).__name__, "extractor", "high")
raw_facts["module"] = FieldValue(type(obj).__module__, "extractor", "high")
raw_facts["attributes"] = list(vars(obj).keys())
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

State dict key names like `encoder.layer.0.attention.self.query.weight` are highly informative for the LLM — they reveal architecture without loading weights.

**OnnxExtractor**
```python
model = onnx.load(path)
raw_facts["opset"] = model.opset_import[0].version
raw_facts["op_types"] = list({n.op_type for n in model.graph.node})
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

`dim_param` captures dynamic axes (e.g. `"batch_size"`, `"sequence_length"`) instead of collapsing them to `0`.

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
    cfg = json.load(open(os.path.join(path, "config.json")))
    raw_facts["hf_config"] = {
        "model_type": cfg.get("model_type"),
        "architectures": cfg.get("architectures"),
        "hidden_size": cfg.get("hidden_size"),
        "num_labels": cfg.get("num_labels"),
        "num_hidden_layers": cfg.get("num_hidden_layers"),
    }

if "tokenizer_config.json" in files:
    raw_facts["tokenizer_class"] = json.load(open(...)).get("tokenizer_class")

if "saved_model.pb" in files:
    raw_facts["format"] = "tf_savedmodel"

if "adapter_config.json" in files:
    raw_facts["is_peft_adapter"] = True
```

No model loading. Pure JSON reads.

---

### Layer 3 — Deep Attribute Scan (best-effort)

Only runs for pickle-loaded objects where Layer 2 succeeded. Extracts sklearn/xgb/lgb/catboost attributes:

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

---

## Artifact Size Policy

| Size | Inspection mode | Behavior |
|---|---|---|
| ≤ 100 MB | `loaded` | Full inspection allowed. Pickle gate still applies. |
| 100 MB – 1 GB | `structural` | Metadata and structural only. No model loading. |
| > 1 GB | `metadata` | No deserialization. Deployment-spec workflow required. |

`inspection_mode` is attached to every `RawFacts` output. Pickle artifacts in `loaded` mode still require the safety gate — size alone is not sufficient to permit deserialization.

---

## Extractor Registry

Extractors are discovered through a registry rather than hardcoded conditionals. This makes the extractor set open for extension without touching inspector core.

```python
class ExtractorRegistry:
    def register(self, extractor: BaseExtractor) -> None: ...
    def resolve(self, path: str, raw_facts: dict) -> BaseExtractor: ...
```

`resolve` iterates registered extractors in priority order and returns the first whose `can_handle(path, raw_facts)` returns `True`. `GenericExtractor` is registered last as the catch-all fallback.

```python
registry = ExtractorRegistry()
registry.register(OnnxExtractor())
registry.register(SafetensorsExtractor())
registry.register(TorchExtractor())
registry.register(DirectoryExtractor())
registry.register(PickleExtractor())
registry.register(GenericExtractor())   # fallback

extractor = registry.resolve(path, raw_facts)
raw_facts = extractor.extract(path, raw_facts)
```

New artifact formats (gguf, mlx, etc.) are added by registering a new extractor — no changes to the inspection pipeline.

---

## Confidence Derivation

Computed from what was actually extracted, not assumed. Uses only `inspection_confidence` — `interpretation_confidence` is set by the LLM response.

```python
def _compute_inspection_confidence(raw_facts: dict) -> str:
    known = sum(1 for k, v in raw_facts.items()
                if k not in ("errors", "artifact_path") and v not in (None, "unknown", []))
    total = len(raw_facts) - 2
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

## Capability Detection

The inspector extracts capabilities independently from framework:

```json
{
  "capabilities": ["predict", "predict_proba"]
}
```

Future examples:

```json
{
  "capabilities": ["embeddings", "text_generation"]
}
```

More useful than framework detection alone — capabilities directly drive the shape of `predict()`.

---

## Safety Classification

Every artifact receives a safety assessment:

```json
{
  "safety": {
    "deserialization_risk": "high",
    "execution_risk": "medium"
  }
}
```

| Format | `deserialization_risk` |
|---|---|
| pickle | high |
| ONNX | low |
| safetensors | low |

Surfaced to users before loading.

---

## ArtifactMetadata

Interpreted fields use `FieldValue` for provenance. Raw structural fields remain plain types.

```python
@dataclass
class ArtifactMetadata:
    # always present — raw measured values, no provenance needed
    artifact_path: str
    artifact_size_mb: float
    extension: str
    inspection_mode: str                   # "metadata" | "structural" | "loaded"
    inspection_cost: str                   # "low" | "medium" | "high"
    inspection_confidence: str             # "high" | "medium" | "low" — from _compute_inspection_confidence
    interpretation_confidence: str         # "high" | "medium" | "low" — set by LLM response, "none" if skipped
    inspection_errors: list[dict]          # [{layer, error}]
    deployment_readiness: str              # "ready" | "needs_clarification" | "unsupported"

    # interpreted fields — carry provenance
    framework: FieldValue | None           # e.g. FieldValue("xgboost", "llm", "medium")
    load_format: FieldValue | None
    input_hint: FieldValue | None
    output_hint: FieldValue | None

    # structural fields — plain types (None = unknown)
    class_name: str | None
    class_hierarchy: list | None
    feature_count: int | None
    class_labels: list | None
    capabilities: list[str] | None
    safety: dict | None

    # passed downstream
    raw_facts: dict = field(default_factory=dict)
```

`inspection_confidence` and `interpretation_confidence` are the only confidence signals. There is no top-level `confidence` field — that would drift and contradict the two specific fields.

`deployment_readiness` values:
- `ready` — framework known, load_format known, no critical unknowns
- `needs_clarification` — framework or load_format unknown, or input format ambiguous
- `unsupported` — format unknown and no extractor could handle it

---

## DeploymentSpec Builder

After Stage 1, `build_deployment_spec(raw_facts)` produces a `DeploymentSpecCandidate` before the LLM is involved. This gives the LLM a partially-filled spec to enrich rather than building from scratch.

```python
@dataclass
class DeploymentSpecCandidate:
    framework: str | None           # from raw_facts["framework"].value if source == "extractor"
    artifact_type: str | None       # from raw_facts["format"]
    loader_strategy: str | None     # from raw_facts["load_format"].value if known
    required_packages: list[str]    # derived from framework (empty if unknown)
    capabilities: list[str]         # from raw_facts["capabilities"]
    deployment_readiness: str       # derived from rules below
```

### Readiness derivation rules

```python
def _derive_readiness(raw_facts: dict) -> str:
    fmt = raw_facts.get("format", "unknown")
    framework = raw_facts.get("framework")
    load_format = raw_facts.get("load_format")

    if fmt == "unknown":
        return "unsupported"

    framework_value = framework.value if isinstance(framework, FieldValue) else framework
    load_format_value = load_format.value if isinstance(load_format, FieldValue) else load_format

    if framework_value is None:
        return "needs_clarification"

    if load_format_value is None:
        return "needs_clarification"

    return "ready"
```

Example candidates:

| Artifact | `deployment_readiness` | Reason |
|---|---|---|
| Clean ONNX with valid graph | `ready` | framework=onnx, load_format known |
| XGBClassifier but xgboost not installed | `needs_clarification` | framework=None (can't import) |
| `.bin` file with no magic bytes match | `unsupported` | format=unknown |
| sklearn Pipeline, all attributes present | `ready` | framework=sklearn, load_format=joblib |

---

## DeploymentSpec

The inspector now produces a `DeploymentSpec` candidate alongside `RawFacts`:

```json
{
  "framework": "sklearn",
  "artifact_type": "pickle",
  "required_packages": ["scikit-learn"],
  "capabilities": ["predict"],
  "deployment_readiness": "ready"
}
```

This becomes the durable contract passed downstream to codegen and packaging. It is enriched by the LLM interpretation stage when confidence is insufficient.

---

## Inspection Cache

Inspection results are cached by artifact hash to avoid redundant work on re-deploy:

Cache key: `artifact_hash` (SHA-256 of artifact bytes)

```json
{
  "artifact_hash": "...",
  "raw_facts": {...},
  "deployment_spec": {...}
}
```

Cache stored at `~/.inference-engine/cache/<hash>-inspect.json`.

---

## Stage 2 — LLM Interpretation

Fires when `deployment_readiness != "ready"`. A dedicated LLM call before codegen. The LLM receives the `DeploymentSpecCandidate` and enriches it rather than building from scratch.

Input: `raw_facts + inspection_errors + DeploymentSpecCandidate + sample_input + --framework hint`

### System prompt

```
You are analyzing a machine learning artifact to determine how to load and run it.
You receive raw structural facts extracted from the artifact file.
Your job is to interpret these facts and fill in missing information.

Return a JSON object with:
- framework: one of sklearn, pytorch, transformers, xgboost, lightgbm, catboost,
             onnx, sentence_transformers, tf_savedmodel, generic
- load_format: how to load the artifact
- input_hint: what predict() receives (specific about shape/type)
- output_hint: what predict() returns
- confidence: "high" | "medium" | "low"
- suggested_sample_input: a concrete example input value inferred from facts
- question: one short specific question if a critical unknown remains, else null
- question_field: which field the question resolves

Only ask a question if it would materially change how load() or predict() is written.
```

### User prompt construction

```python
def _build_interpretation_prompt(raw_facts, spec_candidate, sample_input, framework_hint):
    lines = [
        "Raw facts extracted from artifact:",
        json.dumps(raw_facts, indent=2),
        "\nPartial deployment spec (fill in unknowns):",
        json.dumps(asdict(spec_candidate), indent=2),
    ]

    if sample_input is not None:
        lines.append(f"\nSample input provided by user: {sample_input!r}")
        lines.append("Use this to infer input type and shape.")

    if framework_hint:
        lines.append(f"\nUser specified --framework {framework_hint}. Trust this.")

    if raw_facts.get("errors"):
        lines.append(f"\nInspection errors: {raw_facts['errors']}")
        lines.append("Account for these gaps.")

    lines.append("\nReturn JSON only.")
    return "\n".join(lines)
```

### Clarifying question flow

```python
def _maybe_clarify(meta, answers):
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

Max 2 questions. Questions must materially affect deployment. Non-interactive (`--yes`) mode skips questions entirely.

Good questions: `"Does predict() receive raw text or tokenized inputs?"`
Bad questions: `"What is this model for?"`

---

## `sample_input` in Generation and Fix Prompts

`sample_input` feeds into all three LLM calls — not just validation:

**`generate()` prompt:**
```python
if sample_input is not None:
    lines.append(f"\nSample input: {sample_input!r}")
    lines.append("predict() must handle this exact input type.")
```

**`fix()` prompt:**
```python
user_prompt = (
    f"The following code failed:\n\n```\n{error}\n```\n\n"
    f"Code:\n\n```python\n{previous_code}\n```\n\n"
    f"Artifact metadata:\n{json.dumps(meta_summary)}\n\n"
    f"Sample input used during validation: {sample_input!r}\n\n"
    f"Fix load() and predict(). Return only the two corrected method bodies."
)
```

Without metadata and `sample_input` in the fix prompt, the LLM is fixing blind.

---

## `--framework` Flag

Optional hint that short-circuits framework detection without skipping structural extraction.

```bash
inference-engine deploy ./model.pt --framework pytorch
inference-engine deploy ./model.pkl --framework xgboost
```

Effect:
- Sets `raw_facts["framework_hint"]` as trusted input to LLM interpretation
- If confidence is otherwise sufficient with the hint, skips the clarifying question flow
- Does not suppress inspection errors or skip structural extraction

---

## Extractor Plugin System

All extractors implement:

```python
class BaseExtractor:
    def can_handle(self, path: str, raw_facts: dict) -> bool: ...
    def extract(self, path: str, raw_facts: dict) -> dict: ...
```

Discovery is handled by `ExtractorRegistry` (see above). New artifact types are added by implementing `BaseExtractor` and registering an instance — no changes to inspector core.

Built-in extractors:

```text
extractors/
├── pickle.py       (PickleExtractor — with safety gate)
├── torch.py        (TorchExtractor)
├── onnx.py         (OnnxExtractor)
├── safetensors.py  (SafetensorsExtractor)
├── directory.py    (DirectoryExtractor — HuggingFace, TF SavedModel)
└── generic.py      (GenericExtractor — catch-all fallback)
```

---

## CLI Output

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
  Safety       deserialization_risk: high

Confidence: low — proceeding with LLM interpretation.

? What framework is this model from?
  Detected class: XGBClassifier — is this an XGBoost model? (Y/n) >
```

Rules:
- Never print a raw traceback unless `--verbose` is passed
- Inspection errors go into `meta.inspection_errors`, shown only with `--verbose`
- Always continue past inspection failures — partial metadata is better than nothing
- Confidence level is always shown before codegen

---

## File Changes

| File | Change |
|---|---|
| `app/cli/core/inspector.py` | Replace monolithic script with layered extractors; always exit 0; add `FieldValue`, `DeploymentSpecCandidate`, `ExtractorRegistry`, `_derive_readiness`, `build_deployment_spec`; update `ArtifactMetadata` — remove `confidence`, add `inspection_confidence`, `interpretation_confidence`, `deployment_readiness`, `capabilities`, `safety`; add pickle safety gate; inspection cache |
| `app/cli/core/agent.py` | Add `interpret()` taking `spec_candidate`; enrich `fix()` and `generate()` prompts with metadata + `sample_input`; change LLM trigger from `confidence < high` to `deployment_readiness != ready` |
| `app/cli/core/prompts.py` | Add `framework_hint` and `allow_load` to `DeployAnswers`; clarifying question renderer |
| `app/cli/commands/deploy.py` | Add `--framework`, `--yes`, `--allow-load`; insert spec builder + interpretation + clarify step between inspection and codegen; replace `sys.exit(1)` with graceful continuation |
| `app/cli/__main__.py` | Expose `--framework`, `--yes`, `--allow-load` on CLI |
