# Getting Started

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) or pip
- Docker (only for Postgres + Redis)

---

## Minimal run (no external dependencies)

```bash
git clone <repo>
cd inference-engine
uv sync

uvicorn app.adapters.http.app:app --reload
```

Uses SQLite for job storage and an in-process thread pool for async jobs.

```bash
# Verify it works
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# → {"result": "hello"}
```

---

## Full stack (Postgres + Redis + arq worker)

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` starts Docker services, waits for health, runs the DB migration, launches the arq worker, and starts uvicorn — all in one command.

> **Linux/macOS:** change `VENV=".venv/Scripts"` to `VENV=".venv/bin"` at the top of `dev.sh`.

---

## Development keys

When `API_KEYS` is not set, two hardcoded keys are active:

| Key | Scopes |
|---|---|
| `dev-key` | `predict`, `read_models` |
| `admin-key` | `predict`, `read_models`, `admin` |

Never use these in production.
