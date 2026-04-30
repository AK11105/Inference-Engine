# Authentication

**Files:** `app/security/auth.py`, `app/adapters/http/middleware/auth.py`, `app/security/permissions.py`

---

## API key authentication

Every request except `GET /health` must include:

```
X-API-Key: <your-api-key>
```

`AuthMiddleware` validates the key before the request reaches any route handler.

- Missing key → `401 Unauthorized`
- Unknown key → `401 Unauthorized`
- Insufficient scope → `403 Forbidden`

---

## Key format

Set via `API_KEYS` environment variable:

```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

Each entry: `key:tenant_id:scope1,scope2`. Entries separated by `;`.

Keys are loaded once at startup. To rotate, update `API_KEYS` and restart.

---

## Timing-safe comparison

API key comparison uses `hmac.compare_digest` — constant-time, not short-circuit. This prevents timing attacks where an attacker enumerates valid key prefixes by measuring response time differences.

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

## Development fallback

When `API_KEYS` is not set:

| Key | Tenant | Scopes |
|---|---|---|
| `dev-key` | `tenant_dev` | `predict`, `read_models` |
| `admin-key` | `tenant_admin` | `predict`, `read_models`, `admin` |

**Never use in production.**

---

## Production guard

When `ENV=production` and `API_KEYS` is not set, the server refuses to start:

```
RuntimeError: API_KEYS must be set in production.
Set ENV=development to use hardcoded dev keys.
```

This prevents accidentally deploying with open dev keys.

---

## Production checklist

- [ ] Set `ENV=production`
- [ ] Set `API_KEYS` with strong randomly generated keys
- [ ] Run behind TLS-terminating reverse proxy
- [ ] Restrict `/metrics` and `/debug/*` to internal networks
- [ ] Rotate keys periodically
