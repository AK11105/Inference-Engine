# Routing

**File:** `app/services/routing_service.py`, `app/config/routing.py`

Resolves `(model, None)` → `(model, concrete_version)` when a client omits the `version` field. If the client provides a version, routing is bypassed entirely.

---

## Strategies

![Routing strategies traffic split diagram](../assets/routing-strategies-light.png#only-light)
![Routing strategies traffic split diagram](../assets/routing-strategies-dark.png#only-dark)

### static

Always routes to a fixed version.

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

Deterministic split based on a SHA-256 hash of `X-Request-ID`. The same request ID always routes to the same version. Weights must sum to 100.

```python
"my_model": {
    "strategy": "ab",
    "variants": {"v1": 70, "v2": 30},
}
```

Requires a non-null `X-Request-ID` header. If absent and no version is specified, the request fails with HTTP 400.

---

## Fallback

If no rule exists for a model and the client omits `version`, the request fails with HTTP 400.

---

## Configuration

See [Routing Configuration](../configuration/routing.md).
