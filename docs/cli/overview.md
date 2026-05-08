# CLI Overview

The inference engine ships with a CLI for deploying trained model artifacts without
writing boilerplate by hand.

## Installation

```bash
uv sync --extra cli   # or: pip install -e ".[cli]"
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | API key for LLM code generation |
| `INFERENCE_ENGINE_LLM_MODEL` | No | Override default model (`llama-3.3-70b-versatile`) |

Variables are loaded automatically from `.env` in the project root.

## Commands

| Command | Description |
|---|---|
| `inference-engine deploy <artifact>` | Deploy a trained artifact — inspect, generate, validate, write |
| `inference-engine fix <model-dir>` | Fix a broken existing pipeline definition |

See [deploy.md](deploy.md) and [fix.md](fix.md) for full reference.

## Design constraints

- Only `load()` and `predict()` are ever generated. The pipeline structure,
  pre/postprocessors, and definition file template are fixed.
- No files are written until validation passes and the user confirms.
- The CLI only writes under `models/` and patches `app/config/routing.py`.
  It never modifies engine internals.
- `deploy` is file-only. Restart the server after deploying to load the new model.
