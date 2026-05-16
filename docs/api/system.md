# System Endpoints

---

## GET /health

Liveness check. No authentication required.

**Response `200`:** `{"status": "ok"}`

Use for container liveness probes.

---

## GET /ready

Readiness check. Returns `503` while models are still loading.

**Response `200`:** `{"status": "ready"}`  
**Response `503`:** `{"status": "loading"}`

Use for container readiness probes. Returns `200` only after all pipelines are loaded into memory.

---

## GET /models

List all registered models and versions.

**Required scope:** `read_models`

**Response `200`:**
```json
{"models": [{"name": "echo", "version": "v1"}, {"name": "echo", "version": "v2"}]}
```

Returns all models known to the registry, including those not yet loaded into memory.

---

## GET /metrics

Prometheus metrics in text format.

**Authentication:** None required (public endpoint).

Returns standard Prometheus text exposition format. See [Metrics](../observability/metrics.md).

---

## GET /debug/models/loaded

Lists models currently loaded in memory (warm cache).

**Required scope:** `admin`

**Response `200`:**
```json
{"loaded_models": [{"name": "echo", "version": "v1"}]}
```

After startup warm-up completes, this should match `/models`.

---

## Admin endpoints

See [Admin API](../api/admin.md) for hot-reload and memory management.
