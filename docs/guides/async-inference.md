# Async Inference

Submit long-running inference jobs and poll for results without blocking.

---

## Submit a job

```bash
curl -X POST http://localhost:8000/predict/async \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "my_model", "version": "v1", "data": {"features": [1,2,3]}}'
# → {"job_id": "550e8400-e29b-41d4-a716-446655440000"}
```

Returns immediately with a `job_id`.

---

## Poll for status

```bash
curl -H "X-API-Key: dev-key" \
  http://localhost:8000/predict/async/550e8400-e29b-41d4-a716-446655440000
```

Response when complete:

```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",
  "result": {"label": "positive", "score": 0.97},
  "created_at": "2026-05-13T12:00:00Z",
  "finished_at": "2026-05-13T12:00:01Z"
}
```

---

## Job statuses

| Status | Meaning |
|---|---|
| `pending` | Queued, not yet picked up |
| `running` | Executing |
| `succeeded` | Complete — `result` is populated |
| `failed` | Error — `error_message` is populated |

---

## Batch async

```bash
curl -X POST http://localhost:8000/predict/async/batch \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "my_model", "version": "v1", "items": [{"features": [1,2,3]}, {"features": [4,5,6]}]}'
```

---

## With Redis (recommended for production)

When `REDIS_URL` is set, jobs are enqueued to an arq worker process. This decouples inference from the API server and allows horizontal scaling.

```bash
# Start the worker
arq app.infra.queue.worker.WorkerSettings
```

---

## Without Redis (development)

When `REDIS_URL` is not set, jobs run as `asyncio` tasks on the server's event loop. No worker process needed. Not recommended for production.

---

See [Async Jobs concept](../concepts/async-jobs.md) for architecture details.
