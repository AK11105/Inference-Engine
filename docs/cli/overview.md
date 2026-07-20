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
| `inference-engine logs` | Query the persistent structured event log |

See [deploy.md](deploy.md), [fix.md](fix.md), and [logs.md](logs.md) for full reference.

## Design constraints

- Only `load()` and `predict()` are ever generated. The pipeline structure,
  pre/postprocessors, and definition file template are fixed.
- No files are written until validation passes and the user confirms (or `--yes` is set).
- The `--yes` flag is the explicit non-interactive mode for CI. It skips all
  prompts, auto-approves confirmations, and implies `--allow-load`. All future
  commands must support `--yes` from the start — do not add new commands that
  rely solely on `_is_interactive()`.
- The CLI only writes under `models/` and patches `app/config/routing.py`.
  It never modifies engine internals.
- `deploy` is file-only. Restart the server after deploying to load the new model.
- When generation fails after all retries, a scaffold `definition.py` is written
  with `# TODO` comments instead of raising an error.
- Every interpreted metadata field (framework, input/output hints, load format)
  carries provenance — source and confidence — so the fix loop knows which
  fields are trustworthy vs guessed.
- Format discovery uses a plugin-based `ExtractorRegistry` — new formats are
  supported by registering a `BaseExtractor` subclass without modifying inspector core.
- After extraction, a `DeploymentSpecCandidate` is built with explicit readiness
  rules — the LLM trigger is `deployment_readiness != "ready"`, not a fragile
  confidence heuristic.
- When readiness is not "ready", an LLM interpretation stage enriches metadata
  before codegen fires — preventing codegen from guessing at unknown fields and
  burning retries. The interpretation stage degrades gracefully on failure.
