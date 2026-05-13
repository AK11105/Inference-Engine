# Error Codes

## HTTP status codes

| Code | Meaning |
|---|---|
| `200` | Success |
| `400` | Bad request — validation error, missing version, malformed payload |
| `401` | Unauthorized — missing or invalid API key |
| `403` | Forbidden — API key lacks required scope |
| `404` | Not found — job ID or model not found |
| `413` | Payload too large — body exceeds 1 MB |
| `429` | Too many requests — rate limit exceeded |
| `500` | Internal server error — inference failure or timeout |

---

## Inference error types

These appear in `inference_errors_total{error_type=...}` and in job `error_types` fields.

| Error type | Cause |
|---|---|
| `model_not_found` | No pipeline registered for `(model, version)` |
| `timeout` | Executor timed out (see SLA config) |
| `inference_error` | Any other exception during pipeline execution |

---

## Job statuses

| Status | Meaning |
|---|---|
| `created` | Record created |
| `pending` | Queued, not yet picked up |
| `running` | Executing |
| `succeeded` | Complete — `result` populated |
| `failed` | Error — `error_message` populated |
| `cancelled` | Cancelled before execution |
