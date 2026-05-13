# Troubleshooting

## Server won't start

| Error | Fix |
|---|---|
| `RuntimeError: API_KEYS must be set in production` | Set `API_KEYS` env var or set `ENV=development` |
| `ModuleNotFoundError: No module named 'app'` | Run from project root; check `pythonpath = ["."]` in `pyproject.toml` |
| `unable to open database file` | `mkdir -p app/instance` |
| Postgres connection refused on Windows | Use `127.0.0.1` instead of `localhost` in `DATABASE_URL` |

---

## Inference errors

| Error | Fix |
|---|---|
| `404` on `/predict` | Model not registered — check `models/` directory and restart |
| `400 ModelNotFoundError` | `MODEL_NAME`/`MODEL_VERSION` in `definition.py` don't match the request |
| `400 ValidationError` | Validator rejected the input — check input shape |
| `500 ExecutionTimeoutError` | Increase SLA timeout in `app/config/sla.py` |
| `500 InferenceExecutionError` | Exception in `predict()` — check server logs |

---

## Auth errors

| Error | Fix |
|---|---|
| `401 Unauthorized` | Missing or invalid `X-API-Key` header |
| `403 Forbidden` | Key exists but lacks the required scope |
| `429 Too Many Requests` | Rate limit exceeded — back off and retry |

---

## Async jobs stuck

Jobs stuck in `running` state after a worker crash are reaped automatically:
- At server startup (jobs older than 10 minutes)
- By the arq cron task (every 10 minutes)

To manually check stuck jobs, query the jobs endpoint or the database directly.

---

## arq worker issues

| Problem | Fix |
|---|---|
| Worker exits immediately | Redis not running or `REDIS_URL` not set — unset it to use in-process fallback |
| Jobs not being processed | Check worker is running: `arq app.infra.queue.worker.WorkerSettings` |
| Worker can't find models | Worker initialises its own registry — ensure `models/` is accessible |

---

## dev.sh issues

| Problem | Fix |
|---|---|
| `dev.sh` fails on Linux/macOS | Change `VENV=".venv/Scripts"` → `VENV=".venv/bin"` at the top of `dev.sh` |
| Docker services not starting | Check Docker is running; `docker compose ps` |
