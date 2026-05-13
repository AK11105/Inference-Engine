# CLI Reference

## Commands

| Command | Description |
|---|---|
| `inference-engine deploy <artifact>` | Deploy a trained artifact |
| `inference-engine fix <model-dir>` | Fix a broken pipeline definition |

---

## deploy

```bash
inference-engine deploy <artifact> [options]
```

| Flag | Default | Description |
|---|---|---|
| `--name` | derived from filename | Model name |
| `--version` | auto-incremented | Version string |
| `--device` | `cpu` | `cpu` or `gpu` |
| `--routing` | `static` | `static`, `canary`, or `ab` |
| `--sample-input` | prompted | Sample input for validation |
| `--dry-run` | off | Validate but write nothing |

---

## fix

```bash
inference-engine fix <model-dir>
```

Interactive only. Prompts for sample input and confirmation before writing.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | Yes | Groq API key for LLM generation |
| `INFERENCE_ENGINE_LLM_MODEL` | No | Override LLM model (default: `llama-3.3-70b-versatile`) |
