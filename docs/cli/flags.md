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

## logs flags

| Flag | Default | Description |
|---|---|---|
| `--deployment-id` | none | Filter by deployment correlation ID |
| `--request-id` | none | Filter by request correlation ID |
| `--job-id` | none | Filter by async job ID |
| `--event` | none | Filter by event name (prefix match) |
| `--level` | none | Minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--component` | none | Filter by component name |
| `--model` | none | Filter by model name |
| `--since` | none | Time window, e.g. `5m`, `1h`, `24h`, `7d` |
| `--limit` | `50` | Max rows returned |
| `--format` | `table` | `table` or `json` |
| `--follow` | off | Live tail (poll every 1s) |
| `--stats` | off | Show log store stats |
| `--purge` | off | Purge events older than `--older-than` |
| `--older-than` | `7d` | Age threshold for `--purge` |
| `--yes` / `-y` | off | Skip the `--purge` confirmation prompt |

See [logs.md](logs.md) for examples.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | API key for LLM code generation |
| `INFERENCE_ENGINE_LLM_MODEL` | No | Override default model (`llama-3.3-70b-versatile`) |

Variables are loaded automatically from `.env` in the project root.
