# Local Development

## Setup

```bash
git clone <repo>
cd inference-engine
uv sync          # or: pip install -e ".[dev]"
cp .env.example .env
```

---

## Running

```bash
# Minimal (SQLite + in-process async)
uvicorn app.adapters.http.app:app --reload

# Full stack (Postgres + Redis + arq worker)
bash dev.sh
```

`dev.sh` starts Docker services, waits for Postgres to be ready, runs the DB migration, launches the arq worker, and starts uvicorn.

!!! note
    `dev.sh` now runs everything inside Docker Compose. No host-side venv path configuration is needed.

---

## Tests

```bash
pytest                        # all tests + coverage report
pytest tests/test_phase1.py   # specific file
```

Tests use `httpx.TestClient` — no running server needed. SQLite uses `:memory:` for isolation. Coverage requires ≥ 70%.

---

## Curl tests

```bash
bash tests/curl_test.sh http://localhost:8000
```

Runs end-to-end checks against a live server and writes results to `tests/curl_results.md`.

---

## Useful commands

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

curl $BASE/metrics
curl -H "X-API-Key: admin-key" $BASE/debug/models/loaded
curl -H "X-API-Key: admin-key" $BASE/admin/models/memory
```
