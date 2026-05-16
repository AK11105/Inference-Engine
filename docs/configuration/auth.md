# Auth Configuration

**Files:** `app/security/auth.py`, `app/adapters/http/middleware/auth.py`

---

## Setting API keys

```bash
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

Format: `key:tenant_id:scope1,scope2`. Entries separated by `;`.

Keys are loaded once at startup. To rotate, update `API_KEYS` and restart.

---

## Scopes

| Scope | Grants access to |
|---|---|
| `predict` | `/predict`, `/predict/batch`, `/predict/async*` |
| `read_models` | `/models` |
| `admin` | `/debug/*`, `/admin/*` |

!!! note
    `/metrics`, `/health`, and `/ready` are public endpoints — no API key required.

---

## Production guard

When `ENV=production` and `API_KEYS` is not set, the server refuses to start:

```
RuntimeError: API_KEYS must be set in production.
```

---

## Development fallback

When `API_KEYS` is not set:

| Key | Tenant | Scopes |
|---|---|---|
| `dev-key` | `tenant_dev` | `predict`, `read_models` |
| `admin-key` | `tenant_admin` | `predict`, `read_models`, `admin` |

!!! warning
    Never use in production.
