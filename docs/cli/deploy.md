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
5. Calls the LLM to generate `load()` and `predict()` method bodies using per-framework prompt templates
6. Validates the generated pipeline against the sample input in a temp directory
7. Retries up to 3 times on failure, sending the traceback back to the LLM each time
8. If all retries fail, writes a scaffold `definition.py` with `# TODO` comments instead of exiting with an error
9. Shows a preview of files to be written and asks for confirmation
10. Writes `models/<name>/<version>/definition.py`, copies the artifact, patches `app/config/routing.py`
11. Prints a ready-to-use `curl` command

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

## Supported frameworks

| Framework | Support | Metadata extracted |
|---|---|---|
| sklearn | Full | pipeline steps, feature count, class labels |
| PyTorch (`nn.Module`) | Full | layer count, first/last layer names |
| Transformers (`PreTrainedModel`) | Full | model type, num_labels, tokenizer class |
| XGBoost | Full | n_estimators, objective |
| LightGBM | Full | n_estimators, objective |
| CatBoost | Full | feature count, loss function |
| ONNX (`.onnx` file) | Full | input/output names and shapes |
| sentence-transformers | Full | embedding dimension |
| Generic | Fallback | class name only, LLM fills the gaps |

All framework detections use lazy imports — none of these are required dependencies.
The inspector runs in an isolated subprocess, so missing frameworks degrade gracefully.

## Note on server reload

`deploy` patches `app/config/routing.py`. If the server is running with `--reload`,
this will trigger a hot-reload. Deploy while the server is stopped, or use `--dry-run`
to validate first, then deploy and restart.
