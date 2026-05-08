# CLI Overview

The inference engine ships with a CLI for deploying trained model artifacts without
writing boilerplate by hand.

## Installation

The CLI is an optional extra. Install it alongside the engine:

```bash
uv pip install -e ".[cli]"
```

Required environment variable for LLM-assisted generation:

```bash
export GROQ_API_KEY=<your-key>
```

Override the default model (optional):

```bash
export INFERENCE_ENGINE_LLM_MODEL=llama-3.3-70b-versatile   # default
```

Environment variables are loaded automatically from `.env` in the project root.

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

**Full flow (Phases 1–5, all implemented):**

1. Shows a pickle safety warning and asks for confirmation
2. Inspects the artifact in an isolated subprocess — detects framework, pipeline steps, input/output hints
3. Prompts for name, version, device, routing strategy, and sample input
4. Auto-increments version by scanning `models/<name>/` for existing versions
5. Calls Groq to generate `load()` and `predict()` method bodies
6. Validates the generated pipeline against the sample input in a temp directory
7. Retries generation up to 3 times on validation failure, sending the traceback back to the LLM
8. Shows a preview of files to be written and asks for confirmation
9. Writes `models/<name>/<version>/definition.py`, copies the artifact, and patches `app/config/routing.py`
10. Prints a ready-to-use `curl` command

### Options

| Flag | Description |
|---|---|
| `--name` | Model name (default: derived from filename) |
| `--version` | Version (default: auto-incremented) |
| `--device` | `cpu` or `gpu` (default: `cpu`) |
| `--routing` | `static`, `canary`, or `ab` (default: `static`) |
| `--sample-input` | Sample input for validation |

When all flags are provided, all interactive prompts are skipped (CI-safe).

### Example (non-interactive)

```bash
inference-engine deploy tests/fixtures/sentiment.pkl \
  --name sentiment \
  --version v1 \
  --device cpu \
  --routing static \
  --sample-input "this movie was great"
```

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

- Re-running with the same name/version overwrites the files and replaces the routing entry (no duplicates).
- No files are written until the pipeline passes validation and the user confirms.

### Routing strategies

The `--routing` flag controls the entry written into `app/config/routing.py`:

| Strategy | Behaviour |
|---|---|
| `static` | Always routes to the deployed version |
| `canary` | Routes 10% of traffic to the new version, 90% to primary |
| `ab` | Routes 100% of traffic to the new version via A/B weights |

Edit `app/config/routing.py` directly to adjust percentages after deployment.

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
  (Hot reload via `--hot` is planned but not yet implemented.)
