# Security Model

## Authentication

Every request except `GET /health` must include:

```
X-API-Key: <your-api-key>
```

- Missing key → `401 Unauthorized`
- Unknown key → `401 Unauthorized`
- Insufficient scope → `403 Forbidden`

API key comparison uses `hmac.compare_digest` — constant-time, preventing timing attacks.

---

## Scopes

| Scope | Grants access to |
|---|---|
| `predict` | `/predict`, `/predict/batch`, `/predict/async*` |
| `read_models` | `/models` |
| `admin` | `/metrics`, `/debug/*`, `/admin/*` |

`/health`, `/ready` — no auth required.
`/jobs/{id}` — auth required, no specific scope.

---

## Rate limiting

Per-tenant sliding-window rate limits keyed on `tenant_id`.

| Endpoint | Limit |
|---|---|
| `/predict` | 10 req / 1s |
| `/models` | 2 req / 1s |
| `/metrics` | 10 req / 10s |

Exceeded → `429 Too Many Requests`

**In-process** (`REDIS_URL` not set): per-process counters only. Accurate for single-process deployments.

**Redis-backed** (`REDIS_URL` set): atomic Lua script with sorted set. Accurate across multiple processes.

Every response includes `X-RateLimit-Mode: local` or `X-RateLimit-Mode: distributed`.

---

## Payload guard

Requests with a body larger than **1 MB** are rejected before reaching any route handler → `413 Request Entity Too Large`.

---

## Production checklist

- [ ] Set `ENV=production`
- [ ] Set `API_KEYS` with strong randomly generated keys
- [ ] Run behind TLS-terminating reverse proxy
- [ ] Restrict `/metrics` and `/debug/*` to internal networks
- [ ] Use Redis-backed rate limiting for multi-process deployments

See [Auth Configuration](../configuration/auth.md).
