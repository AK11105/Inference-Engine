# Async Jobs

**Files:** `app/services/async_inference_service.py`, `app/infra/queue/`, `app/domain/jobs/`

Every inference request — sync or async — creates a `Job` record for a full audit trail.

---

## Job lifecycle

![Async job state machine diagram](../assets/async-job-state-machine-light.png#only-light)
![Async job state machine diagram](../assets/async-job-state-machine-dark.png#only-dark)

`PENDING` is set immediately on creation. `RUNNING` is set when the executor picks up the job. `SUCCEEDED` or `FAILED` is set on completion.

---

## Async submission

```python
job_id = await service.submit(model, version, payload, tenant_id)
job    = await service.get(job_id)
```

On `submit()`:
1. Creates a `Job` record (status: `PENDING`).
2. If Redis is available → enqueues to arq worker.
3. If no Redis → schedules as `asyncio.create_task` on the event loop.

Both paths are transparent to clients — the API contract is identical.

---

## arq Worker

```bash
arq app.infra.queue.worker.WorkerSettings
```

| Task | What it does |
|---|---|
| `run_inference` | Transitions job `RUNNING → SUCCEEDED/FAILED`, runs `pipeline.run(payload)` |
| `run_batch_inference` | Same, but runs `pipeline.run_batch(payloads)` |
| `reap_stuck_jobs` | Cron: marks `RUNNING` jobs older than 10 min as `FAILED` |

**Settings:** `max_jobs=10`, `job_timeout=300s`. Cron runs every 10 minutes.

---

## Job stores

**SQLiteJobStore** — default when `DATABASE_URL` is not set. Stored at `app/instance/jobs.db`. WAL mode enabled. Sync operations offloaded to thread pool.

**PostgresJobStore** — used when `DATABASE_URL` is set. Backed by `asyncpg`. Schema auto-created on first startup.

---

## Stuck-job reaper

When a worker process is killed while a job is `RUNNING`, that job stays stuck. The reaper fixes this:

- **On startup:** marks any `RUNNING` job older than 10 minutes as `FAILED`.
- **arq cron:** runs every 10 minutes in the worker process.
