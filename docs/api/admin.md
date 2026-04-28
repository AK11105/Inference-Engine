# Admin API

All admin endpoints require the `admin` scope (`admin-key` in development).

---

## POST /admin/models/{name}/{version}/reload

Hot-reload a single model pipeline without restarting the server.

Evicts the cached pipeline and rebuilds it from its registered `build_pipeline()` definition. In-flight requests using the old pipeline complete normally; subsequent requests get the new one.

**Required scope:** `admin`

**Response `200`:**
```json
{"reloaded": true, "model": "echo", "version": "v1"}
```

**Errors:** `404` if the model/version is not registered. `403` if the key lacks `admin` scope.

**Example:**
```bash
curl -X POST http://localhost:8000/admin/models/echo/v1/reload \
  -H "X-API-Key: admin-key"
```

---

## GET /admin/models/memory

Returns the current state of the model pipeline cache.

**Required scope:** `admin`

**Response `200`:**
```json
{
  "loaded": 2,
  "max_loaded": null,
  "models": [
    {"name": "echo", "version": "v1"},
    {"name": "echo", "version": "v2"}
  ]
}
```

| Field | Description |
|---|---|
| `loaded` | Number of pipelines currently in memory |
| `max_loaded` | LRU cap (`null` = unlimited) |
| `models` | Pipelines in LRU order (most-recently-used last) |

**Example:**
```bash
curl http://localhost:8000/admin/models/memory \
  -H "X-API-Key: admin-key"
```
