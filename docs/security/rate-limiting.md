# Rate Limiting

**Files:** `app/security/rate_limit.py`, `app/adapters/http/middleware/rate_limit.py`

Per-tenant sliding-window rate limits. Keyed on `tenant_id` — all keys belonging to the same tenant share a bucket.

---

## Limits

| Endpoint | Limit |
|---|---|
| `/predict` | 10 req / 1s |
| `/models` | 2 req / 1s |
| `/metrics` | 10 req / 10s |

Exceeded → `429 Too Many Requests`

---

## Backends

**In-process (`RateLimiter`)** — used when `REDIS_URL` is not set. Each process has its own independent counter. Accurate for single-process deployments.

**Redis (`RedisRateLimiter`)** — used when `REDIS_URL` is set. Uses a sorted set per `(limiter_name, tenant_id)` with `ZADD` / `ZREMRANGEBYSCORE`. Accurate across multiple server processes.

The middleware selects the backend automatically at startup.

---

## Payload guard

Requests with a body larger than **1 MB** are rejected before reaching any route handler.

`413 Request Entity Too Large`

Configured in `app/adapters/http/middleware/payload_guard.py`:

```python
MAX_BYTES = 1_000_000
```
