# Async Queue

**Files:** `app/services/async_inference_service.py`, `app/infra/queue/queue.py`, `app/infra/queue/worker.py`

Handles fire-and-forget inference. Degrades gracefully to an in-process thread pool when Redis is unavailable.

---

## AsyncInferenceService

```python
# app/services/async_inference_service.py
service = AsyncInferenceService(prediction_service, job_queue=None)

job_id = await service.submit(model, version, payload, tenant_id)
job_id = await service.submit_batch(model, version, payloads, tenant_id)
job    = service.get(job_id)
```

On `submit()`:
1. Creates a `Job` record (status: `PENDING`).
2. If `job_queue` is set → enqueues to arq. The arq worker picks it up and runs inference.
3. If `job_queue` is `None` → calls `executor.submit_background(run)` in the same process.

The `job_queue` is wired in at startup by the FastAPI lifespan hook if `REDIS_URL` is set.

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

The worker initialises its own `ModelRegistry` and `JobService` at startup (`on_startup` hook). It shares the same job store as the API server — both read/write the same database.

**Tasks:**

| Task | What it does |
|---|---|
| `run_inference` | Transitions job `RUNNING → SUCCEEDED/FAILED`, runs `pipeline.run(payload)` |
| `run_batch_inference` | Same, but runs `pipeline.run_batch(payloads)` |

**Settings** (in `worker.py`):

| Setting | Default | Description |
|---|---|---|
| `max_jobs` | 10 | Concurrent jobs per worker process |
| `job_timeout` | 300s | Seconds before a job is considered timed out |
| `redis_settings` | from `REDIS_URL` env var | Redis connection |

Run multiple worker processes for higher throughput.

---

## Fallback path (no Redis)

When `REDIS_URL` is not set, `AsyncInferenceService` calls `executor.submit_background()` directly. The job runs in the same process as the API server, in the background thread pool. No arq worker is needed.

This is transparent to clients — the API contract is identical.
