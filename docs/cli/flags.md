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
| `--yes` / `-y` | off | Skip all confirmation prompts (CI mode). Implies `--allow-load`. |

When all flags are provided, all interactive prompts are skipped (CI-safe).

!!! tip "CI mode with `--yes`"
    `--yes` is the explicit, reliable way to run non-interactively. It skips all confirmation prompts (deserialization gate, write confirmation, interpreter clarifying questions) and auto-accepts defaults. Prefer `--yes` over relying on TTY detection in CI pipelines.

!!! warning "Pickle safety"
    Without `--allow-load`, pickle/joblib artifacts receive metadata-only inspection (Layer 2 skipped). `--yes` implies `--allow-load` — deserialization proceeds without prompting.

---

## fix flags

| Flag | Default | Description |
|---|---|---|
| `--sample-input` | prompted interactively | Sample input for pipeline validation |
| `--yes` / `-y` | off | Skip all confirmation prompts (CI mode) |

```bash
inference-engine fix <model-dir> --sample-input "test input" --yes
```

!!! note
    With `--yes`, `--sample-input` is required — there is no interactive fallback to prompt for it.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | API key for LLM code generation |
| `INFERENCE_ENGINE_LLM_MODEL` | No | Override default model (`llama-3.3-70b-versatile`) |

Variables are loaded automatically from `.env` in the project root.
