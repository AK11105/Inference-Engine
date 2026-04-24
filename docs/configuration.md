# Configuration

---

## Routing Configuration

**Location:** `app/config/routing.py`

The `ROUTES` dict maps model names to routing strategies. Routing is applied when a request omits the `version` field (or passes `null`). Explicit versions always bypass routing.

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

### Routing Strategies

#### `static`

Always routes to a fixed version.

```python
"stable_model": {
    "strategy": "static",
    "version": "v3",
}
```

#### `canary`

Routes a percentage of traffic to the canary version; the rest goes to primary.

```python
"echo": {
    "strategy": "canary",
    "primary": "v1",
    "canary": "v2",
    "canary_percent": 20,   # 20% → v2, 80% → v1
}
```

- `canary_percent`: integer 1–100. Uses `random.randint(1, 100)`.
- Set to `100` for deterministic testing (all traffic → canary).
- Set to `0` to effectively disable canary.

#### `ab`

Deterministic A/B split based on a hash of the `identity_key` (request ID). Requires the caller to supply a consistent identity key for sticky routing.

```python
"classifier": {
    "strategy": "ab",
    "variants": {
        "v1": 50,   # 50% of traffic
        "v2": 50,   # 50% of traffic
    },
}
```

- Weights must sum to 100.
- Uses SHA-256 of the identity key modulo 100 for bucket assignment.
- Raises `ValueError` if no identity key is provided.

### Routing Resolution Rules

1. If `version` is explicitly provided in the request → use it directly, skip routing.
2. If `version` is `null` or omitted → look up `ROUTES[model_name]` and apply strategy.
3. If no routing config exists for the model → raise `ValueError`.

---

## Execution Policy

**Location:** `app/config/execution.py`

The `EXECUTION_POLICY` dict maps `"model:version"` keys to named executors. The `DEFAULT_EXECUTOR` is used for any model not explicitly listed.

```python
EXECUTION_POLICY = {
    "echo:v1": "gpu",
    "echo:v2": "cpu",
}

DEFAULT_EXECUTOR = "cpu"
```

**Available executors:**

| Name | Workers | Use case |
|---|---|---|
| `cpu` | 8 | CPU-bound models, default |
| `gpu` | 2 | GPU-bound models |

Executor instances are created in `app/adapters/http/deps.py` and are singletons per process.

**Behavior:**
- If `"echo:v1"` is mapped to `"gpu"`, all inference for that model/version runs in the GPU thread pool.
- If a mapping references an unknown executor name, a `RuntimeError` is raised at inference time.
- There is no silent fallback — misconfigured policies fail loudly.

---

## Executor Settings

Executor parameters are set in `app/adapters/http/deps.py`:

```python
@lru_cache
def get_cpu_executor():
    return InferenceExecutor(device="cpu", max_workers=8)

@lru_cache
def get_gpu_executor():
    return InferenceExecutor(device="gpu", max_workers=2)
```

The default timeout for sync inference is `10.0` seconds (set on the base executor in `get_executor()`). Per-request timeouts can be passed via `PredictionService.predict(timeout_s=...)`.

---

## Job Store

**Location:** `app/infra/jobs/sqlite_job_store.py`

Default path: `app/instance/jobs.db`

The SQLite database is created automatically on first startup. The schema is:

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    model_name   TEXT NOT NULL,
    model_version TEXT NOT NULL,
    payload      TEXT NOT NULL,   -- JSON-serialized
    status       TEXT NOT NULL,
    device       TEXT NOT NULL,
    created_at   TEXT NOT NULL,   -- ISO 8601
    started_at   TEXT,
    finished_at  TEXT,
    result       TEXT,            -- JSON-serialized
    error_type   TEXT,
    error_message TEXT
)
```

To use a different path, modify the `SQLiteJobStore` instantiation in `deps.py`:

```python
_job_store = SQLiteJobStore(db_path="/path/to/jobs.db")
```

---

## Payload Size Limit

**Location:** `app/adapters/http/middleware/payload_guard.py`

```python
MAX_BYTES = 1_000_000  # 1 MB
```

Applies to all `POST` and `PUT` requests. Returns `413` if exceeded.

---

## Rate Limits

**Location:** `app/adapters/http/middleware/rate_limit.py`

```python
LIMITS = {
    "/predict": RateLimiter(rate=10, per_seconds=1),
    "/models":  RateLimiter(rate=2,  per_seconds=1),
    "/metrics": RateLimiter(rate=1,  per_seconds=10),
}
```

Rate limits are per API key using a sliding window algorithm. Returns `429` when exceeded.

---

## Logging

**Location:** `app/core/logging.py`

Structured JSON logging is configured at startup via `setup_logging()`. All log records are emitted as JSON to stdout.

Log format:
```json
{
  "timestamp": "2026-04-24T13:00:00.000000",
  "level": "INFO",
  "message": "inference_success",
  "request_id": "abc-123",
  "job_id": "550e8400-...",
  "model": "echo",
  "version": "v1",
  "latency_ms": 2.4
}
```

Log level is `INFO` by default.
