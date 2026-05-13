# Production Deployment

---

## Environment

```bash
cp .env.example .env
```

Required for production:

```bash
ENV=production
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/inference_engine
REDIS_URL=redis://localhost:6379/0
```

When `ENV=production` and `API_KEYS` is not set, the server refuses to start.

---

## Start services

```bash
bash dev.sh
```

Or manually:

```bash
# 1. Start Postgres + Redis
docker compose up -d

# 2. Start arq worker
arq app.infra.queue.worker.WorkerSettings &

# 3. Start API server
uvicorn app.adapters.http.app:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Reverse proxy

Run behind nginx or a load balancer for TLS termination. Example nginx config:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header X-Request-ID $request_id;
}
```

Passing `X-Request-ID` enables deterministic A/B routing and request correlation in logs.

---

## Security checklist

- [ ] `ENV=production`
- [ ] `API_KEYS` set with strong randomly generated keys
- [ ] TLS-terminating reverse proxy in front
- [ ] `/metrics` and `/debug/*` restricted to internal networks
- [ ] Redis-backed rate limiting (`REDIS_URL` set)

---

## Scaling

- **API server:** run multiple uvicorn workers or processes. Rate limiting requires `REDIS_URL` for cross-process accuracy.
- **arq worker:** run multiple worker processes. Each worker initialises its own model registry.
- **Model registry:** `max_loaded` limits memory usage when many models are registered.

---

## SLA timeouts

Configure per-model timeout budgets in `app/config/sla.py`:

```python
SLA_TIMEOUTS = {
    "heavy_model:v1": 30.0,
    "fast_model:v1":   2.0,
}
DEFAULT_TIMEOUT_S = None  # no global timeout
```

See [Configuration: Execution](../configuration/execution.md).
