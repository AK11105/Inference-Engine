# Async Queue

**Files:** `app/services/async_inference_service.py`, `app/infra/queue/queue.py`, `app/infra/queue/worker.py`

Handles fire-and-forget inference. Degrades gracefully to an in-process async task when Redis is unavailable.

---

## AsyncInferenceService

```python
# app/services/async_inference_service.py
service = AsyncInferenceService(prediction_service, job_queue=None)

job_id = await service.submit(model, version, payload, tenant_id)
job_id = await service.submit_batch(model, version, payloads, tenant_id)
job    = await service.get(job_id)
```

On `submit()`:
1. Creates a `Job` record (status: `PENDING`).
2. If `job_queue` is set → enqueues to arq. The arq worker picks it up and runs inference.
3. If `job_queue` is `None` → schedules `_fallback_run` as an `asyncio.create_task` on the running event loop.

The `job_queue` is wired in at startup by the FastAPI lifespan hook if `REDIS_URL` is set.

Both the single and batch fallback paths log errors at `ERROR` level if the job fails, before marking it `FAILED` in the store.

---

## ArqJobQueue

```python
# app/infra/queue/queue.py
queue = await create_queue(redis_url)   # returns None if Redis is unreachable

await queue.enqueue_inference(job_id, model, version, payload)
await queue.enqueue_batch_inference(job_id, model, version, payloads)
```

`create_queue()` returns `None` on any connection failure — the service falls back silently.

---

## arq Worker

**Run:**
```bash
arq app.infra.queue.worker.WorkerSettings
```

The worker initialises its own `ModelRegistry` and `JobService` at startup (`on_startup` hook), including an async `PostgresJobStore` if `DATABASE_URL` is set. It shares the same job store as the API server.

**Tasks:**

| Task | What it does |
|---|---|
| `run_inference` | Transitions job `RUNNING → SUCCEEDED/FAILED`, runs `pipeline.run(payload)` |
| `run_batch_inference` | Same, but runs `pipeline.run_batch(payloads)` |
| `reap_stuck_jobs` | Cron: marks `RUNNING` jobs older than 10 min as `FAILED` |

**Settings** (in `worker.py`):

| Setting | Default | Description |
|---|---|---|
| `max_jobs` | 10 | Concurrent jobs per worker process |
| `job_timeout` | 300s | Seconds before a job is considered timed out by arq |
| `redis_settings` | from `REDIS_URL` env var | Redis connection |

**Cron schedule:** `reap_stuck_jobs` runs at minutes 0, 10, 20, 30, 40, 50 of every hour.

---

## Fallback path (no Redis)

When `REDIS_URL` is not set, `AsyncInferenceService` schedules `_fallback_run` as an `asyncio.create_task`. The job runs on the server's event loop using `loop.run_in_executor` for the CPU-bound pipeline call. No arq worker is needed.

This is transparent to clients — the API contract is identical.

**Note:** The stuck-job reaper cron only runs in the arq worker. In the fallback path, stuck jobs from previous crashes are reaped at server startup instead.
