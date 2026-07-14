# CLI Flags Reference

## deploy flags

| Flag | Default | Description |
|---|---|---|
| `--name` | derived from filename | Model name |
| `--version` | auto-incremented | Version string (e.g. `v1`, `v2`) |
| `--device` | `cpu` | `cpu` or `gpu` |
| `--routing` | `static` | `static`, `canary`, or `ab` |
| `--sample-input` | prompted interactively | Sample input for pipeline validation |
| `--framework` | auto-detected | Override/assert model framework (`sklearn`, `pytorch`, `transformers`, etc.) |
| `--dry-run` | off | Run full flow including validation but write nothing |
| `--allow-load` | off | Permit pickle/joblib deserialization during inspection |

When all flags are provided, all interactive prompts are skipped (CI-safe).

!!! warning "Pickle safety"
    Without `--allow-load`, pickle/joblib artifacts receive metadata-only inspection (Layer 2 skipped). In non-interactive/CI mode, `--allow-load` must be explicit — the gate does not auto-approve.

---

## fix flags

`inference-engine fix <model-dir>` takes no flags. It is interactive-only and requires a TTY.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | API key for LLM code generation |
| `INFERENCE_ENGINE_LLM_MODEL` | No | Override default model (`llama-3.3-70b-versatile`) |

Variables are loaded automatically from `.env` in the project root.
