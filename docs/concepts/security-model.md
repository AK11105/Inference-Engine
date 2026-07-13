# Security Model

## Authentication

![Request filtering funnel diagram](../assets/request-filtering-tunnel-light.png#only-light)
![Request filtering funnel diagram](../assets/request-filtering-tunnel-dark.png#only-dark)

Every request except public endpoints must include:

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
| `admin` | `/debug/*`, `/admin/*` |

`/health`, `/ready`, `/metrics` — no auth required (public endpoints).
`/jobs/{id}` — auth required, no specific scope.

---

## Rate limiting

Per-tenant sliding-window rate limits keyed on `tenant_id`.

| Endpoint | Limit |
|---|---|
| `/predict` | 10 req / 1s |
| `/models` | 2 req / 1s |

Exceeded → `429 Too Many Requests`

**In-process** (`REDIS_URL` not set): per-process counters only. Accurate for single-process deployments.

**Redis-backed** (`REDIS_URL` set): atomic Lua script with sorted set. Accurate across multiple processes.

Every response includes `X-RateLimit-Mode: local` or `X-RateLimit-Mode: distributed`.

---

## Payload guard

Requests with a body larger than **1 MB** are rejected before reaching any route handler → `413 Request Entity Too Large`.

---

## Artifact deserialization safety (CLI)

Pickle deserialization executes arbitrary Python code. The CLI inspector gates pickle/joblib loading behind an explicit opt-in (`--allow-load` flag) to prevent untrusted artifacts from compromising the deploy machine.

**Three conditions must be met for deserialization:**

1. `inspection_mode == "loaded"` (artifact ≤ 100 MB)
2. User passed `--allow-load` or confirmed the prompt in interactive mode
3. `safety.deserialization_risk` has been computed and shown

Without opt-in, pickle artifacts receive metadata-only treatment: Layer 0 (filesystem) and Layer 1 (format detection) run; Layer 2 (structural extraction via deserialization) is skipped.

Non-pickle formats (ONNX, safetensors, PyTorch with `weights_only=True`) are not gated — they use safe-by-design loading mechanisms.

See [`--allow-load` in the deploy docs](../cli/deploy.md#pickle-safety-gate) for full details.

---

## Production checklist

- [ ] Set `ENV=production`
- [ ] Set `API_KEYS` with strong randomly generated keys
- [ ] Run behind TLS-terminating reverse proxy
- [ ] Restrict `/metrics` and `/debug/*` to internal networks
- [ ] Use Redis-backed rate limiting for multi-process deployments

See [Auth Configuration](../configuration/auth.md).
