# Development

## Setup

```bash
uv sync          # or: pip install -e ".[dev]"
cp .env.example .env
```

## Running

```bash
# Minimal (SQLite + in-process async)
uvicorn app.adapters.http.app:app --reload

# Full stack (Postgres + Redis + arq worker)
bash dev.sh
```

`dev.sh` starts Docker services, waits for Postgres to be ready, runs the DB migration, launches the arq worker, and starts uvicorn.

## Tests

```bash
pytest                        # all tests + coverage report
pytest tests/test_phase1.py   # specific phase
```

Tests use `httpx.TestClient` — no running server needed. SQLite uses `:memory:` for isolation. Coverage is measured automatically; the suite requires ≥ 70% total coverage.

## Curl tests

```bash
bash tests/curl_test.sh http://localhost:8000
```

Runs 35 end-to-end checks against a live server and writes results to `tests/curl_results.md`.

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
curl -H "X-API-Key: admin-key" $BASE/admin/models/memory
```

## Common issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run pytest from project root; `pythonpath = ["."]` must be in `pyproject.toml` |
| `unable to open database file` | `mkdir -p app/instance` |
| arq worker exits immediately | Redis not running or `REDIS_URL` not set — unset it to use in-process fallback |
| `dev.sh` fails on Linux/macOS | Change `VENV=".venv/Scripts"` → `VENV=".venv/bin"` |
| Postgres connection refused on Windows | Use `127.0.0.1` instead of `localhost` in `DATABASE_URL` — Windows may resolve `localhost` to `::1` (IPv6) which Docker doesn't bind |
