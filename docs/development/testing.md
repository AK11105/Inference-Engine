# Testing

## Run tests

```bash
pytest                        # all tests + coverage
pytest tests/test_phase1.py   # specific file
pytest -k "test_predict"      # filter by name
```

Coverage requires ≥ 70% total. Report is printed automatically.

---

## Test setup

Tests use `httpx.TestClient` — no running server needed. SQLite uses `:memory:` for full isolation between test runs.

Binary test fixtures (e.g. `tests/fixtures/sentiment.pkl`) are generated automatically by `tests/conftest.py` at pytest startup if they don't exist — no manual setup required.

```python
# Example test pattern
from httpx import TestClient
from app.adapters.http.app import app

client = TestClient(app)

def test_predict():
    response = client.post(
        "/predict",
        json={"model": "echo", "version": "v1", "data": "hello"},
        headers={"X-API-Key": "dev-key"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "hello"
```

---

## End-to-end tests

```bash
# Start the server first
uvicorn app.adapters.http.app:app &

bash tests/curl_test.sh http://localhost:8000
```

Results are written to `tests/curl_results.md`.

---

## Common issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run pytest from project root; check `pythonpath = ["."]` in `pyproject.toml` |
| `unable to open database file` | Set `SQLITE_DB_PATH=:memory:` or `mkdir -p app/instance` |
| Coverage below 70% | Add tests for new code paths before merging |
