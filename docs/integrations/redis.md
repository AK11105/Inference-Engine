# Redis

Redis enables two features: distributed async job queuing (arq) and cross-process rate limiting.

---

## Configuration

```bash
REDIS_URL=redis://localhost:6379/0
```

When `REDIS_URL` is not set, both features degrade gracefully:
- Async jobs run as in-process `asyncio` tasks
- Rate limiting is per-process only

---

## Start Redis

```bash
docker compose up -d   # uses the included docker-compose.yml
```

Or run directly:

```bash
docker run -p 6379:6379 redis:7-alpine
```

---

## Start the arq worker

```bash
arq app.infra.queue.worker.WorkerSettings
```

The worker connects to Redis using `REDIS_URL` and processes inference jobs.

---

## Worker settings

| Setting | Default | Description |
|---|---|---|
| `max_jobs` | 10 | Concurrent jobs per worker process |
| `job_timeout` | 300s | Seconds before arq considers a job timed out |

Edit `app/infra/queue/worker.py` to adjust.
