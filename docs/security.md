# Security

---

## Authentication

**Location:** `app/security/auth.py`, `app/adapters/http/middleware/auth.py`

Authentication uses static API keys passed in the `X-API-Key` request header. Each key resolves to an `Identity` object:

```python
@dataclass(frozen=True)
class Identity:
    api_key: str
    tenant_id: str
    scopes: Set[str]
```

The `AuthMiddleware` runs on every request except `/health`. It:
1. Reads `X-API-Key` from headers.
2. Calls `authenticate(api_key)` to look up the identity.
3. Attaches `identity` and `tenant_id` to `request.state`.
4. Returns `401` if the key is missing or invalid.

**Public endpoints (no auth required):**
- `GET /health`

**Current key store:** In-memory dict in `app/security/auth.py`. Replace with a database lookup for production.

---

## Authorization (Scopes)

**Location:** `app/security/permissions.py`

Authorization is scope-based. Each `Identity` carries a set of allowed scopes. Route handlers call `require_scope()` to enforce access:

```python
def require_scope(identity, scope: str) -> None:
    if scope not in identity.scopes:
        raise PermissionError(f"Missing Scope: {scope}")
```

**Scope → endpoint mapping:**

| Scope | Endpoints |
|---|---|
| `predict` | `POST /predict`, `POST /predict/batch`, `POST /predict/async`, `POST /predict/async/batch`, `GET /predict/async/{job_id}`, `GET /jobs/{job_id}` |
| `read_models` | `GET /models` |
| `admin` | `GET /metrics`, `GET /debug/models/loaded` |

`PermissionError` is caught at the route level and returned as `403`.

---

## Rate Limiting

**Location:** `app/security/rate_limit.py`, `app/adapters/http/middleware/rate_limit.py`

Rate limiting uses a **sliding window** algorithm per API key. The `RateLimiter` class tracks request timestamps in a deque and evicts entries outside the window on each check.

```python
class RateLimiter:
    def __init__(self, rate: int, per_seconds: int): ...
    def allow(self, key: str) -> bool: ...
```

**Current limits:**

| Endpoint | Rate | Window |
|---|---|---|
| `/predict` | 10 requests | 1 second |
| `/models` | 2 requests | 1 second |
| `/metrics` | 1 request | 10 seconds |

The `RateLimitMiddleware` applies limits after authentication (so unauthenticated requests are rejected before rate checking). Returns `429` when a limit is exceeded.

**Note:** The current implementation is in-memory and per-process. For multi-process deployments, replace with a Redis-backed rate limiter.

---

## Payload Guard

**Location:** `app/adapters/http/middleware/payload_guard.py`

Rejects `POST` and `PUT` requests with bodies exceeding 1 MB. Returns `413 Payload Too Large`.

```python
MAX_BYTES = 1_000_000  # 1 MB
```

This middleware runs before authentication to prevent large payloads from consuming resources.

---

## Middleware Execution Order

Middleware is applied in reverse registration order in Starlette. The effective order for an incoming request is:

```
1. PayloadGuardMiddleware   → reject oversized bodies (413)
2. AuthMiddleware           → reject unauthenticated requests (401)
3. RateLimitMiddleware      → reject rate-exceeded requests (429)
4. request_id_middleware    → attach/echo X-Request-ID
5. Route handler            → require_scope() → business logic
```

---

## Production Hardening Checklist

The current implementation is suitable for development and internal use. Before exposing to the internet:

- [ ] Replace in-memory API key store with a database or secrets manager
- [ ] Add key rotation and expiry
- [ ] Replace in-memory rate limiter with Redis-backed distributed limiter
- [ ] Add HTTPS (TLS termination at load balancer or via reverse proxy)
- [ ] Audit and tighten CORS policy if browser clients are involved
- [ ] Consider JWT-based auth for stateless horizontal scaling
- [ ] Add request signing or HMAC verification for high-trust integrations
