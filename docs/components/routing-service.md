# Routing Service

**File:** `app/services/routing_service.py`

Resolves `(model, None)` → `(model, concrete_version)` when a client omits the `version` field. If the client provides a version, it is used as-is — routing is bypassed entirely.

---

## How it works

```python
routing_service.resolve(model="echo", requested_version=None, identity_key="req-123")
# → ("echo", "v1")  or  ("echo", "v2")  depending on strategy
```

Rules are configured in `app/config/routing.py`. If no rule exists for a model and the client omits `version`, a `ValueError` is raised → HTTP 400.

---

## Strategies

### static

Always routes to a fixed version. No randomness.

```python
"my_model": {"strategy": "static", "version": "v2"}
```

### canary

Routes `canary_percent`% of traffic to the canary version, the rest to primary. Uses `random.randint` — not deterministic per request.

```python
"my_model": {
    "strategy": "canary",
    "primary": "v1",
    "canary": "v2",
    "canary_percent": 10,
}
```

### ab

Deterministic split based on a SHA-256 hash of `identity_key` (the `X-Request-ID`). The same request ID always routes to the same version. Weights must sum to 100.

```python
"my_model": {
    "strategy": "ab",
    "variants": {"v1": 70, "v2": 30},
}
```

Requires `identity_key` to be non-null. If `X-Request-ID` is absent and no version is specified, the request fails.

---

## Configuration

See [Routing Configuration](../configuration/routing.md).
