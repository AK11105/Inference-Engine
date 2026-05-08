# deploy

Deploy a trained model artifact to the inference engine.

```bash
inference-engine deploy <artifact> [options]
```

## What it does

1. Shows a pickle safety warning and asks for confirmation
2. Inspects the artifact in an isolated subprocess — detects framework, pipeline steps, input/output hints
3. Prompts for name, version, device, routing strategy, and sample input
4. Auto-increments version by scanning `models/<name>/` for existing versions
5. Calls the LLM to generate `load()` and `predict()` method bodies
6. Validates the generated pipeline against the sample input in a temp directory
7. Retries up to 3 times on failure, sending the traceback back to the LLM each time
8. Shows a preview of files to be written and asks for confirmation
9. Writes `models/<name>/<version>/definition.py`, copies the artifact, patches `app/config/routing.py`
10. Prints a ready-to-use `curl` command

## Options

| Flag | Default | Description |
|---|---|---|
| `--name` | derived from filename | Model name |
| `--version` | auto-incremented | Version string |
| `--device` | `cpu` | `cpu` or `gpu` |
| `--routing` | `static` | `static`, `canary`, or `ab` |
| `--sample-input` | prompted | Sample input for validation |
| `--dry-run` | off | Run full flow including validation but write nothing |

When all flags are provided, all interactive prompts are skipped (CI-safe).

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

Dry run — validate but write nothing:

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
        ├── definition.py     ← generated
        └── <artifact>        ← copied here
```

`app/config/routing.py` is patched to add the model's routing entry.
Re-running with the same name/version overwrites files and replaces the routing entry — no duplicates.

## Routing strategies

| Strategy | What gets written |
|---|---|
| `static` | Always routes to the deployed version |
| `canary` | 10% to new version, 90% to primary — edit `routing.py` to adjust |
| `ab` | 100% weight on new version via A/B dict — edit `routing.py` to adjust |

## Supported frameworks

| Framework | Support |
|---|---|
| sklearn | Full — pipeline steps, feature count, class labels inferred automatically |
| xgboost | Partial — class name and basic hints |
| PyTorch | Not supported — use the [manual flow](../guides/adding-a-model.md) |
| Generic | Fallback — class name only, LLM fills the gaps |
