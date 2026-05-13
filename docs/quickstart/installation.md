# Installation

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker — only needed for Postgres + Redis

---

## Install

```bash
git clone <repo>
cd inference-engine
uv sync          # or: pip install -e .
```

---

## Start the server

```bash
uvicorn app.adapters.http.app:app --reload
```

The server starts on `http://localhost:8000`. No external dependencies required — SQLite handles job storage and an in-process thread pool handles async jobs.

---

## Verify

```bash
curl http://localhost:8000/health
# -> {"status": "ok"}

curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# -> {"result": "hello"}
```

---

## Development API keys

When `API_KEYS` is not set, two hardcoded keys are active:

| Key | Scopes |
|---|---|
| `dev-key` | `predict`, `read_models` |
| `admin-key` | `predict`, `read_models`, `admin` |

!!! warning
    Never use these keys in production. See [Auth Configuration](../configuration/auth.md).

---

Next: [First Deployment](first-deployment.md)
