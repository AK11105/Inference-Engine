# Development

## Setup

```bash
uv sync          # or: pip install -e .
cp .env.example .env
```

## Running

```bash
# Minimal (SQLite + in-process async)
uvicorn app.adapters.http.app:app --reload

# Full stack
bash dev.sh      # starts Docker, arq worker, uvicorn
```

## Tests

```bash
pytest                        # all
pytest tests/test_phase1.py   # specific phase
```

Tests use `httpx.TestClient` — no running server needed. SQLite uses `:memory:` for isolation.

## Useful curl commands

```bash
BASE=http://localhost:8000

curl $BASE/health
curl $BASE/ready
curl -H "X-API-Key: dev-key" $BASE/models

# Sync inference
curl -X POST $BASE/predict \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","data":"hello"}'

# Async inference
curl -X POST $BASE/predict/async \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" \
  -d '{"model":"echo","version":"v1","data":"hello"}'

# Poll job (replace <id>)
curl -H "X-API-Key: dev-key" $BASE/predict/async/<id>

curl -H "X-API-Key: admin-key" $BASE/metrics
curl -H "X-API-Key: admin-key" $BASE/debug/models/loaded
```

Full script: `tests/curl_test.sh`

## Common issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run pytest from project root; `pythonpath = ["."]` must be in `pyproject.toml` |
| `unable to open database file` | `mkdir -p app/instance` |
| arq worker exits immediately | Redis not running or `REDIS_URL` not set — unset it to use in-process fallback |
| `dev.sh` fails on Linux/macOS | Change `VENV=".venv/Scripts"` → `VENV=".venv/bin"` |
