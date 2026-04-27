# Structured Logging

**File:** `app/core/logging.py`

All log output is JSON, written to stdout. Configured once at startup via `setup_logging()`.

---

## Base format

Every log line:

```json
{
  "timestamp": "2026-04-27T15:00:00+00:00",
  "level": "INFO",
  "message": "inference_success"
}
```

---

## Inference success fields

```json
{
  "timestamp": "...",
  "level": "INFO",
  "message": "inference_success",
  "request_id": "550e8400-...",
  "job_id": "7f3e1a2b-...",
  "model": "echo",
  "version": "v1",
  "tenant_id": "tenant_dev",
  "latency_ms": 3.2
}
```

---

## Request ID propagation

Every request gets an `X-Request-ID`:
- Client sends one → echoed back in response header and included in logs.
- Client omits it → UUID generated, same propagation.

Use this to correlate a client request → server log → job record.

---

## Shipping logs

Pipe stdout to your log collector. The JSON format is already structured — no additional parsing needed for Datadog, Loki, CloudWatch, etc.
