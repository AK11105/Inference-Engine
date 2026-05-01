# CLI Overview

The inference engine ships with a CLI for deploying trained model artifacts without
writing boilerplate by hand.

## Installation

The CLI is an optional extra. Install it alongside the engine:

```bash
uv pip install -e ".[cli]"
```

Required environment variable for LLM-assisted generation (Phase 3+):

```bash
export OPENAI_API_KEY=<your-key>        # default provider
export ANTHROPIC_API_KEY=<your-key>     # if using anthropic
# ollama requires no key
```

Set `INFERENCE_ENGINE_LLM_PROVIDER=anthropic` or `ollama` to switch providers.

## Commands

| Command | Description |
|---|---|
| `inference-engine deploy <artifact>` | Deploy a model artifact to the engine |
| `inference-engine fix <model-dir>` | Fix a broken existing pipeline (Phase 6) |

---

## `deploy`

```bash
inference-engine deploy ./sentiment.pkl
```

**What it does (current — Phase 1):**
- Shows a pickle safety warning and asks for confirmation
- Inspects the artifact in an isolated subprocess
- Prints detected framework, pipeline structure, input/output hints

**What it will do (Phases 2-5):**
- Prompt for name, version, device, routing strategy, sample input
- Generate `load()` and `predict()` via LLM
- Validate the pipeline before writing anything
- Write `models/<name>/<version>/definition.py` and copy the artifact
- Patch `app/config/routing.py`

### Options

| Flag | Description |
|---|---|
| `--name` | Model name (default: derived from filename) |
| `--version` | Version (default: auto-incremented) |
| `--device` | `cpu` or `gpu` (default: `cpu`) |
| `--routing` | `static`, `canary`, or `ab` (default: `static`) |
| `--sample-input` | Sample input for validation |

When all flags are provided, all interactive prompts are skipped (CI-safe).

### Supported artifact types

| Framework | Support |
|---|---|
| sklearn | Full — pipeline steps, feature count, class labels inferred automatically |
| xgboost | Partial — class name and basic hints |
| PyTorch | Not yet supported — use the [manual flow](../guides/adding-a-model.md) |
| Generic | Fallback — class name only, LLM fills the gaps |

### File output

```
models/
└── <name>/
    └── <version>/
        ├── definition.py     <- generated
        └── <artifact>        <- copied here
```

`app/config/routing.py` is patched to add the new model's routing entry.
No files are written until the pipeline passes validation and the user confirms.

---

## `fix`

```bash
inference-engine fix models/sentiment/v1/
```

Reads an existing `definition.py`, runs it through the validation loop, and if it
fails sends the error + code to the LLM for a fix. Shows a diff before writing.

Available in Phase 6.

---

## Design constraints

- Only `load()` and `predict()` are ever generated. The pipeline structure,
  pre/postprocessors, and definition file template are fixed.
- No files are written until validation passes and the user confirms.
- The CLI never modifies engine internals. It only writes under `models/` and
  patches `app/config/routing.py`.
- `deploy` is file-only. Restart the server after deploying to load the new model.
