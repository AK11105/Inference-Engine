# deploy

Deploy a trained model artifact to the inference engine.

```bash
inference-engine deploy <artifact> [options]
```

## What it does

![CLI deploy flowchart](../assets/cli-deploy-light.png#only-light)
![CLI deploy flowchart](../assets/cli-deploy-dark.png#only-dark)

1. **Inspect** — runs the artifact through format-specific extractors in an isolated subprocess, returning structured metadata
2. **Spec build** — derives a `DeploymentSpecCandidate` from raw facts (framework, artifact type, loader strategy, readiness)
3. **Interpret** _(new)_ — if `deployment_readiness != "ready"`, calls an LLM to fill in ambiguous fields (framework, load format, input/output hints). In interactive mode, may ask up to 2 multiple-choice clarifying questions. Skipped entirely when the artifact is already fully understood.
4. Prompts for name, version, device, routing strategy, and sample input
5. Auto-increments version by scanning `models/<name>/` for existing versions
6. Shows a preview of files to be written
7. In `--dry-run` mode, exits here — no codegen LLM call, no files written
8. **Codegen** — calls the LLM to generate `load()` and `predict()` method bodies using per-framework prompt templates (with enriched metadata from the interpretation stage)
9. Validates the generated pipeline against the sample input in a temp directory
10. Retries up to 3 times on failure, sending the traceback back to the LLM each time
11. If all retries fail, writes a scaffold `definition.py` with `# TODO` comments instead of exiting with an error
12. Asks for confirmation, then writes `models/<name>/<version>/definition.py`, copies the artifact, patches `app/config/routing.py`
13. Prints a ready-to-use `curl` command

## Options

| Flag | Default | Description |
|---|---|---|
| `--name` | derived from filename | Model name |
| `--version` | auto-incremented | Version string |
| `--device` | `cpu` | `cpu` or `gpu` |
| `--routing` | `static` | `static`, `canary`, or `ab` |
| `--sample-input` | prompted | Sample input for validation |
| `--framework` | auto-detected | Override/assert the model framework: `sklearn`, `pytorch`, `transformers`, `xgboost`, `lightgbm`, `catboost`, `onnx`, or `sentence_transformers` |
| `--dry-run` | off | Show preview and exit — no LLM call, no files written |
| `--allow-load` | off | Permit pickle/joblib deserialization during inspection (see [Pickle safety gate](#pickle-safety-gate)) |

When all flags are provided, all interactive prompts are skipped (CI-safe).

### `--framework`

Auto-detection inspects the artifact structurally (`isinstance` checks against each framework's classes) and needs that framework's package installed in the CLI's environment to succeed. If it isn't installed, detection falls back to `generic` and codegen has to guess from the class name alone.

`--framework` asserts the framework explicitly, skipping that guesswork:

```bash
inference-engine deploy ./model.pkl --framework xgboost
```

It's recorded as `raw_facts["framework_hint"]` before extraction runs and takes priority over the detected framework for code generation — it does not skip or alter structural extraction itself, so inspection errors are still surfaced normally.

### `--allow-load` (pickle safety gate) {#pickle-safety-gate}

Pickle deserialization executes arbitrary Python code. Loading an untrusted `.pkl` or `.joblib` artifact can compromise the machine running the inspector. The safety gate prevents this by requiring explicit opt-in.

**Behavior by mode:**

| Mode | `--allow-load` present? | What happens |
|---|---|---|
| Interactive | No | User is prompted "Continue with deserialization? (Y/n)" |
| Interactive | Yes | Deserialization proceeds without prompt |
| Non-interactive (CI) | No | Deserialization skipped — metadata-only inspection |
| Non-interactive (CI) | Yes | Deserialization proceeds |

**When deserialization is skipped:**

- Layer 0 (filesystem) and Layer 1 (format detection) still run
- Layer 2 (structural extraction) is skipped for pickle/joblib formats
- `deployment_readiness` is set to `needs_clarification`
- An error is recorded: `"pickle deserialization skipped — use --allow-load to permit"`
- The LLM interpretation stage still fires (with limited metadata)

**Safety metadata:**

Every inspected artifact receives a `safety` dict in `raw_facts`:

```json
{
  "safety": {
    "deserialization_risk": "high",
    "execution_risk": "medium"
  }
}
```

Risk levels by format:

| Format | `deserialization_risk` | `execution_risk` |
|---|---|---|
| pickle / joblib | `high` | `medium` |
| pytorch (.pt/.pth) | `low` | `low` |
| onnx | `none` | `none` |
| safetensors | `none` | `none` |
| directory | `none` | `low` |

**Size limit:** Pickle artifacts larger than 100 MB are never deserialized, even with `--allow-load`.

**CI example with full inspection:**

```bash
inference-engine deploy ./sentiment.pkl \
  --name sentiment --version v1 \
  --device cpu --routing static \
  --sample-input "this movie was great" \
  --allow-load
```

## Examples

Interactive:

```bash
inference-engine deploy ./sentiment.pkl
```

Non-interactive (CI):

```bash
inference-engine deploy ./sentiment.pkl \
  --name sentiment --version v1 \
  --device cpu --routing static \
  --sample-input "this movie was great"
```

Dry run — inspect and preview without calling the LLM or writing anything:

```bash
inference-engine deploy ./sentiment.pkl --dry-run \
  --name sentiment --version v1 \
  --device cpu --routing static \
  --sample-input "great movie"
```

## File output

```
models/
└── <name>/
    └── <version>/
        ├── definition.py     ← generated (or scaffold if generation failed)
        └── <artifact>        ← copied here
```

`app/config/routing.py` is patched to add the model's routing entry.
Re-running with the same name/version overwrites files and replaces the routing entry — no duplicates.

## Scaffold fallback

When the LLM cannot produce a passing pipeline after 3 attempts, a scaffold is written instead of failing:

```
Scaffold written. Complete the TODOs before deploying.
  models/<name>/<version>/definition.py  [scaffold — fill in load() and predict()]
```

The scaffold is valid Python that imports correctly but raises `NotImplementedError` at runtime until the `# TODO` sections are filled in. The artifact is still copied and routing is still patched.

## Routing strategies

| Strategy | What gets written |
|---|---|
| `static` | Always routes to the deployed version |
| `canary` | 10% to new version, 90% to primary — edit `routing.py` to adjust |
| `ab` | 100% weight on new version via A/B dict — edit `routing.py` to adjust |

## Supported formats and frameworks

Format is detected from file extension and magic bytes before any loading attempt.

| Format / Extension | Extractor | Load strategy | Metadata extracted |
|---|---|---|---|
| `.pkl`, `.pickle` | PickleExtractor | `joblib.load` → `pickle.load` | class name, pipeline steps, feature count, class labels |
| `.joblib` | PickleExtractor | `joblib.load` | same as pickle |
| `.pt`, `.pth` | TorchExtractor | `torch.load(..., weights_only=True)` | state dict keys (up to 30), param count, or layer names |
| `.onnx` | OnnxExtractor | `onnx.load` | opset, op types, inputs/outputs with dynamic axes |
| `.safetensors` | SafetensorsExtractor | header-only read | tensor keys, shapes, metadata |
| directory | DirectoryExtractor | JSON reads only | `config.json` fields, tokenizer class, PEFT adapter flag |
| unknown | GenericExtractor | `joblib.load` → `pickle.load` | class name, errors recorded |

Framework detection (sklearn, PyTorch, Transformers, XGBoost, LightGBM, CatBoost, sentence-transformers) runs as a second pass for pickle-loaded objects.

All framework libraries use lazy imports — none are required dependencies.
The inspector runs in an isolated subprocess and always exits 0; extraction errors are recorded in metadata rather than crashing the deploy pipeline.

## Extractor registry (plugin-based)

Format discovery is handled by the `ExtractorRegistry` — a priority-ordered collection of `BaseExtractor` subclasses. Adding support for a new format requires zero changes to inspector core.

### Architecture

```
app/cli/core/extractors/
├── __init__.py              # default_registry() factory
├── base.py                  # BaseExtractor ABC
├── registry.py              # ExtractorRegistry (register/resolve/list)
├── builtin.py               # Re-exports all built-in extractors
├── pickle_extractor.py      # .pkl, .pickle, .joblib
├── torch_extractor.py       # .pt, .pth
├── onnx_extractor.py        # .onnx
├── safetensors_extractor.py # .safetensors
├── directory_extractor.py   # HF model dirs, TF SavedModel
└── generic_extractor.py     # Catch-all fallback (priority 0)
```

### Adding a custom extractor

```python
from app.cli.core.extractors import BaseExtractor, default_registry

class GGUFExtractor(BaseExtractor):
    name = "gguf"
    priority = 70  # higher = tried first

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("format") == "gguf"

    def extract(self, path: str, raw_facts: dict) -> dict:
        # Parse GGUF header, populate raw_facts
        raw_facts["framework"] = "llama_cpp"
        raw_facts["quantization"] = "Q4_K_M"
        return raw_facts

# Register it
registry = default_registry()
registry.register(GGUFExtractor())
```

### How resolution works

1. `default_registry()` returns a fresh registry pre-loaded with all built-in extractors
2. `registry.resolve(path, raw_facts)` iterates extractors in descending priority order
3. The first extractor whose `can_handle()` returns `True` wins
4. `GenericExtractor` (priority 0) always matches — it's the fallback

### BaseExtractor interface

| Method / Attribute | Description |
|---|---|
| `name` | Human-readable identifier (e.g. `"onnx"`) |
| `priority` | Integer; higher = tried first. Built-ins use 60, generic uses 0 |
| `can_handle(path, raw_facts) -> bool` | Return `True` if this extractor should handle the artifact |
| `extract(path, raw_facts) -> dict` | Populate and return the `raw_facts` dict with extracted metadata |

## LLM interpretation stage

When `deployment_readiness` is not `"ready"` (i.e. framework or load format is unknown/ambiguous), the deploy pipeline calls an LLM to interpret the raw inspection facts before codegen runs. This prevents codegen from guessing blindly and burning retries on wrong assumptions.

### What it does

- Receives the raw inspection facts, deployment spec, inspection errors, framework hint, and sample input
- Returns a structured JSON with: `framework`, `load_format`, `input_hint`, `output_hint`, `confidence`, and optionally a clarifying question
- Patches `ArtifactMetadata` fields with the LLM's interpretation (source: `"llm"`)
- Respects source priority: user-provided values (`--framework`) are never overwritten

### Clarifying questions (interactive mode)

When the LLM cannot confidently determine a field, it may return a question with multiple-choice options:

```
? Is this an XGBModel or a raw Booster? (load_format)
  [1] joblib (recommended)
  [2] xgb.Booster + load_model()
  [3] pickle
  (Press Enter for recommended)
  >
```

- At most 2 questions per deploy
- The LLM's best guess is tagged `(recommended)`
- Pressing Enter accepts the recommended option
- In non-interactive mode (`--yes` / CI), the recommended answer is auto-accepted

### Skip conditions

| Condition | Behavior |
|---|---|
| `deployment_readiness == "ready"` | Stage skipped entirely — no LLM call |
| `GROQ_API_KEY` not set | Warning printed, stage skipped |
| LLM call fails (network error) | Warning printed, pipeline continues with unpatched metadata |
| LLM returns invalid JSON | Warning printed, pipeline continues with unpatched metadata |

### Integration point

```python
from app.cli.core.interpreter import interpret, apply_interpretation
from app.cli.core.spec_builder import build_deployment_spec

spec = build_deployment_spec(meta.raw_facts)
if spec.deployment_readiness != "ready":
    result = interpret(meta, spec, sample_input=answers.sample_input, interactive=is_tty)
    if result is not None:
        meta = apply_interpretation(meta, result)
```

### Overwrite rules

The interpretation stage uses smart priority logic to decide whether to patch each field:

| Existing field state | LLM result | Outcome |
|---|---|---|
| `None` | any value | LLM wins |
| value is `"unknown"` / `"generic"` / `""` | any value | LLM wins |
| source is `"default"` | any value | LLM wins |
| source is `"extractor"`, value is meaningful | any value | Extractor wins |
| source is `"user"` | any value | User always wins |

## Field provenance

Every interpreted metadata field (framework, input hint, output hint, load format) carries provenance information via `FieldValue`:

```python
from app.cli.core.inspector import FieldValue

# Each interpreted field tracks:
#   value      — the actual data ("sklearn", "raw text string", etc.)
#   source     — where it came from ("filesystem", "extractor", "llm", "user", "default")
#   confidence — how certain ("high", "medium", "low")
```

This enables the fix loop to know which fields are trustworthy vs guessed, and powers the explain mode output:

```
framework: sklearn (source: extractor, confidence: high)
input_hint: raw text string (source: extractor, confidence: high)
```

Source hierarchy when values conflict: `user > extractor > llm > default`.

Raw structural fields (class_name, feature_count, class_labels, etc.) remain plain types — they are measured directly, not interpreted.

### Confidence fields

Metadata carries two separate confidence signals:

| Field | Meaning |
|---|---|
| `inspection_confidence` | How successful the extractor was (derived from extraction completeness and errors) |
| `interpretation_confidence` | How reliable the interpreted fields are (derived from framework detection quality) |

## Deployment readiness (spec builder)

After extraction, `build_deployment_spec(raw_facts)` produces a `DeploymentSpecCandidate` that decides whether the LLM interpretation stage is needed:

```python
from app.cli.core.spec_builder import build_deployment_spec

spec = build_deployment_spec(meta.raw_facts)
# spec.deployment_readiness is one of: "ready", "needs_clarification", "unsupported"
```

### Readiness rules

| Condition | Result | Meaning |
|---|---|---|
| `format == "unknown"` or missing | `unsupported` | Cannot proceed — artifact format is unrecognized |
| `framework` is None/unknown/generic | `needs_clarification` | LLM must interpret to determine framework |
| `load_format` is None/missing | `needs_clarification` | LLM must determine how to load the artifact |
| All three present and valid | `ready` | LLM can be skipped — enough info to generate code directly |

### DeploymentSpecCandidate fields

| Field | Type | Description |
|---|---|---|
| `framework` | `str \| None` | Detected ML framework (sklearn, pytorch, etc.) |
| `artifact_type` | `str \| None` | Normalized format (pickle, pytorch, onnx, directory) |
| `loader_strategy` | `str \| None` | How to load (joblib, state_dict, from_pretrained, etc.) |
| `required_packages` | `list[str]` | Runtime Python packages needed |
| `capabilities` | `list[str]` | Detected model capabilities (predict, predict_proba) |
| `deployment_readiness` | `str` | "ready", "needs_clarification", or "unsupported" |

## Note on server reload

No restart is needed to serve a newly deployed model — call
`POST /admin/models/{name}/{version}/reload` after `deploy` finishes and it
becomes available immediately, even if the server was already running when
you deployed. See [Admin API](../api/admin.md).

`deploy` also patches `app/config/routing.py`, which controls default-version
routing (canary/A/B) when a request omits `version`. That file is only read
at process startup, so a routing change (as opposed to the model itself)
still requires a restart to take effect. If the server is running with
`--reload`, writing `routing.py` will trigger uvicorn's own file-watcher
restart — harmless, just not required for the model to be servable.
