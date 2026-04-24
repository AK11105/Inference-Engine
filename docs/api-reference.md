# API Reference

Base URL: `http://localhost:8000`

---

## Authentication

All endpoints except `/health` and `/ready` require an API key passed in the `X-API-Key` header.

```
X-API-Key: dev-key
```

**Built-in keys (development only):**

| Key | Tenant | Scopes |
|---|---|---|
| `dev-key` | `tenant_dev` | `predict`, `read_models` |
| `admin-key` | `tenant_admin` | `predict`, `read_models`, `admin` |

**Error responses:**

| Condition | Status | Body |
|---|---|---|
| Missing header | `401` | `{"detail": "Missing API Key"}` |
| Invalid key | `401` | `{"detail": "Invalid API Key"}` |
| Insufficient scope | `403` | `{"detail": "Missing Scope: <scope>"}` |

---

## Request ID

Every request is assigned a unique `X-Request-ID`. You may supply your own:

```
X-Request-ID: my-trace-id-123
```

The same ID is echoed back in the response headers.

---

## Endpoints

### Health

#### `GET /health`

Liveness probe. No authentication required.

**Response `200`:**
```json
{"status": "ok"}
```

---

#### `GET /ready`

Readiness probe. No authentication required.

**Response `200`:**
```json
{"status": "ready"}
```

---

### Inference

#### `POST /predict`

Synchronous single-item inference. Blocks until the result is ready.

**Required scope:** `predict`

**Request body:**
```json
{
  "model": "echo",
  "version": "v1",
  "data": {"x": 42}
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | `string` | Yes | Registered model name |
| `version` | `string` | No | Explicit version. If omitted, routing rules apply |
| `data` | `any` | Yes | Arbitrary input payload |

**Response `200`:**
```json
{"result": {"echo": {"x": 42}}}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | Model not found, routing misconfiguration |
| `500` | Inference execution error, timeout |

---

#### `POST /predict/batch`

Synchronous batch inference. Processes all items in a single pipeline call.

**Required scope:** `predict`

**Request body:**
```json
{
  "model": "echo",
  "version": "v1",
  "items": [
    {"x": 1},
    {"x": 2},
    {"x": 3}
  ]
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | `string` | Yes | Registered model name |
| `version` | `string` | No | Explicit version |
| `items` | `array` | Yes | Non-empty list of input payloads |

**Response `200`:**
```json
{
  "results": [
    {"echo": {"x": 1}},
    {"echo": {"x": 2}},
    {"echo": {"x": 3}}
  ]
}
```

---

#### `POST /predict/async`

Asynchronous single-item inference. Returns a job ID immediately; inference runs in the background.

**Required scope:** `predict`

**Request body:**
```json
{
  "model": "echo",
  "version": "v1",
  "data": {"x": 99}
}
```

**Response `200`:**
```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000"}
```

---

#### `GET /predict/async/{job_id}`

Poll the status of an async inference job.

**Required scope:** `predict`

**Path parameter:** `job_id` — UUID returned from `POST /predict/async`

**Response `200`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-24T13:00:00",
  "result": {"echo": {"x": 99}},
  "error_message": null
}
```

**Job status values:**

| Status | Meaning |
|---|---|
| `created` | Job record created |
| `pending` | Queued for execution |
| `running` | Actively executing |
| `succeeded` | Completed successfully; `result` is populated |
| `failed` | Execution failed; `error_message` is populated |
| `cancelled` | Job was cancelled (reserved) |

**Error responses:**

| Status | Condition |
|---|---|
| `404` | Job ID not found |

---

#### `POST /predict/async/batch`

Asynchronous batch inference. Returns a job ID immediately.

**Required scope:** `predict`

**Request body:**
```json
{
  "model": "echo",
  "version": "v1",
  "items": [{"x": 1}, {"x": 2}]
}
```

**Response `200`:**
```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000"}
```

Poll status using `GET /predict/async/{job_id}`. The `result` field will be an array when the job succeeds.

---

### Jobs

#### `GET /jobs/{job_id}`

Retrieve raw job metadata.

**Required scope:** `predict`

**Response `200`:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "succeeded",
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-24T13:00:00"
}
```

---

### Models

#### `GET /models`

List all registered model names and versions.

**Required scope:** `read_models`

**Response `200`:**
```json
{
  "models": [
    {"name": "echo", "version": "v1"},
    {"name": "echo", "version": "v2"}
  ]
}
```

---

### Observability

#### `GET /metrics`

Prometheus metrics in text exposition format.

**Required scope:** `admin`

**Response `200`:** Prometheus text format (Content-Type: `text/plain`)

```
# HELP inference_requests_total Total inference requests
# TYPE inference_requests_total counter
inference_requests_total{model="echo",version="v1"} 42.0
...
```

---

#### `GET /debug/models/loaded`

List models currently loaded in memory (i.e., cached in the registry).

**Required scope:** `admin`

**Response `200`:**
```json
{
  "loaded_models": [
    {"name": "echo", "version": "v1"}
  ]
}
```

---

## Global Constraints

| Constraint | Value |
|---|---|
| Max request body size | 1 MB |
| Rate limit: `/predict` | 10 req/s per API key |
| Rate limit: `/models` | 2 req/s per API key |
| Rate limit: `/metrics` | 1 req per 10s per API key |

**Rate limit exceeded response:**
```json
{"detail": "Rate Limit Exceeded"}
```
Status: `429`

**Payload too large response:**
```json
{"detail": "Payload too large"}
```
Status: `413`
