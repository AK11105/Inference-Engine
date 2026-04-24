# Observability

---

## Prometheus Metrics

**Location:** `app/core/metrics.py`

All metrics use a dedicated `CollectorRegistry` (not the default global registry). They are exposed at `GET /metrics` (requires `admin` scope).

### Inference Metrics

#### `inference_requests_total`
- **Type:** Counter
- **Labels:** `model`, `version`
- **Description:** Total number of inference requests received (sync and async).
- **Incremented:** At the start of `_run_inference_with_existing_job()` and `_run_batch_with_existing_job()`.

```
inference_requests_total{model="echo",version="v1"} 42.0
```

#### `inference_errors_total`
- **Type:** Counter
- **Labels:** `model`, `version`, `error_type`
- **Description:** Total inference errors, broken down by error category.
- **Error type values:**

| `error_type` | Cause |
|---|---|
| `model_not_found` | `(model, version)` not in registry |
| `timeout` | Executor timed out |
| `inference_error` | Any other exception during pipeline execution |

```
inference_errors_total{model="echo",version="v1",error_type="timeout"} 1.0
```

#### `inference_latency_seconds`
- **Type:** Histogram
- **Labels:** `model`, `version`
- **Description:** End-to-end inference latency in seconds (from executor submit to result).
- **Buckets:** `0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10`

```
inference_latency_seconds_bucket{model="echo",version="v1",le="0.01"} 38.0
inference_latency_seconds_sum{model="echo",version="v1"} 0.312
inference_latency_seconds_count{model="echo",version="v1"} 42.0
```

### Executor Metrics

#### `executor_inflight`
- **Type:** Gauge
- **Labels:** `device`
- **Description:** Number of inference calls currently executing in the thread pool.
- **Incremented** on `executor.submit()` entry, **decremented** on exit (via `finally`).

```
executor_inflight{device="cpu"} 3.0
executor_inflight{device="gpu"} 0.0
```

#### `executor_timeouts_total`
- **Type:** Counter
- **Labels:** `device`
- **Description:** Total number of executor timeouts.

```
executor_timeouts_total{device="cpu"} 0.0
executor_timeouts_total{device="gpu"} 0.0
```

---

## Accessing Metrics

```bash
curl http://localhost:8000/metrics -H "X-API-Key: admin-key"
```

The response is in Prometheus text exposition format and can be scraped directly by a Prometheus server.

**Prometheus scrape config example:**
```yaml
scrape_configs:
  - job_name: inference-engine
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics
    params:
      # Note: Prometheus cannot pass custom headers natively.
      # Use a proxy or expose metrics on a separate internal port.
```

For production, consider exposing metrics on a separate internal port without authentication, accessible only within the cluster.

---

## Structured Logging

**Location:** `app/core/logging.py`

All log output is JSON-formatted and written to stdout. The `JSONFormatter` produces records like:

```json
{
  "timestamp": "2026-04-24T13:00:00.123456",
  "level": "INFO",
  "message": "inference_success",
  "request_id": "abc-123",
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "model": "echo",
  "version": "v1",
  "latency_ms": 2.4
}
```

**Log events emitted by `PredictionService`:**

| Event | Level | Fields |
|---|---|---|
| `inference_success` | `INFO` | `request_id`, `job_id`, `model`, `version`, `latency_ms` |

Errors are propagated as exceptions and logged by the framework or caller.

**Log level:** `INFO` (set in `setup_logging()`). Change to `DEBUG` for verbose output during development.

---

## Request Tracing

Every request is assigned a `request_id` (UUID) via the `request_id_middleware` in `app.py`. The ID is:
- Read from the incoming `X-Request-ID` header if present.
- Generated as a new UUID if not provided.
- Echoed back in the `X-Request-ID` response header.
- Passed through to `PredictionService` and included in log records.

This enables end-to-end tracing across logs when a consistent `X-Request-ID` is supplied by the client.

---

## Job State as Observability

The job lifecycle (`CREATED → PENDING → RUNNING → SUCCEEDED/FAILED`) stored in SQLite provides a durable audit trail for every inference request. Query the job store directly or via `GET /jobs/{job_id}` to inspect:

- When a job was created, started, and finished
- Which model and version handled it
- The result or error for post-hoc debugging
