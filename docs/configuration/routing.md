# Routing Configuration

**File:** `app/config/routing.py`

Controls version resolution when a client omits `"version"` in the request body. If no rule exists for a model and the client omits version, the request fails with HTTP 400.

---

## Strategies

### static

```python
"my_model": {"strategy": "static", "version": "v2"}
```

Always routes to a fixed version.

### canary

```python
"my_model": {
    "strategy": "canary",
    "primary": "v1",
    "canary": "v2",
    "canary_percent": 10,   # 10% to v2
}
```

Routes `canary_percent`% of traffic to the canary version using `random.randint` — not deterministic per request.

### ab

```python
"my_model": {
    "strategy": "ab",
    "variants": {"v1": 70, "v2": 30},   # must sum to 100
}
```

Deterministic split based on SHA-256 hash of `X-Request-ID`. Same request ID always routes to the same version. Requires a non-null request ID.

---

## Current defaults

```python
ROUTES = {
    "echo": {
        "strategy": "canary",
        "primary": "v1",
        "canary": "v2",
        "canary_percent": 50,
    },
}
```

See [RoutingService component](../components/routing-service.md) for implementation details.
