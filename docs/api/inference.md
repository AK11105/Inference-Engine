# Inference Endpoints

All require `X-API-Key` with `predict` scope.

---

## POST /predict

Synchronous single inference. Blocks until result is ready.

**Request:**
```json
{"model": "echo", "version": "v1", "data": <any>}
```
`version` is optional — omit to use routing rules.

**Response `200`:**
```json
{"result": <any>}
```

**Errors:** `400` model/input error · `500` execution error · `429` rate limit · `413` payload too large

---

## POST /predict/batch

Synchronous batch. All items run through the same model.

**Request:**
```json
{"model": "echo", "version": "v1", "items": [<item>, ...]}
```
`items` must have at least one element.

**Response `200`:**
```json
{"results": [<result>, ...]}
```
Results are in the same order as `items`.

---

## POST /predict/async

Submit a job and return immediately.

**Request:** same shape as `/predict` (`data` field).

**Response `200`:**
```json
{"job_id": "550e8400-..."}
```

---

## GET /predict/async/{job_id}

Poll job status.

**Response `200`:**
```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-27T15:00:00+00:00",
  "result": <value or null>,
  "error_message": <string or null>
}
```

| Status | Meaning |
|---|---|
| `created` | Record created, not yet queued |
| `pending` | Queued, waiting for worker |
| `running` | Worker executing |
| `succeeded` | Done — `result` populated |
| `failed` | Failed — `error_message` populated |
| `cancelled` | Cancelled |

**Errors:** `404` job not found

---

## POST /predict/async/batch

Submit a batch job asynchronously.

**Request:** same shape as `/predict/batch` (`items` field).

**Response `200`:**
```json
{"job_id": "550e8400-..."}
```

When succeeded, `result` from the status endpoint is a list in the same order as `items`.
