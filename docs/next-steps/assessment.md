# Codebase Assessment

## Overview

A production-grade, task-agnostic ML inference backend built on FastAPI. The architecture is
clean, the layering is consistently enforced, and the operational concerns (auth, rate limiting,
observability, async jobs) are addressed at a level well above average for a personal project.

**Overall rating: 8.5 / 10**

---

## Layer Map

```
app/
├── adapters/http/          HTTP boundary — FastAPI, middleware, routes, schemas
├── config/                 Static config — routing rules, execution policy, SLA timeouts
├── core/                   Cross-cutting — logging, metrics, tracing
├── domain/                 Pure ML logic — models, pipelines, registry, jobs, loaders
├── execution/              Executor abstractions — ThreadPool, ONNX, Triton
├── infra/                  I/O implementations — SQLite/Postgres job stores, arq queue
├── security/               Auth, scopes, rate limiting
└── services/               Orchestration — prediction, async inference, routing, jobs
```

The invariant "core ML logic never imports FastAPI or HTTP concepts" is upheld throughout.
No domain file imports from `adapters/`, `services/`, or `infra/`.

---

## Component Assessments

### HTTP Adapter (`adapters/http/`)

**Strengths**
- Clean middleware stack: Auth → RateLimit → PayloadGuard, applied in the right order.
- Request ID propagation via `X-Request-ID` header, generated if absent.
- Lifespan handler correctly warms the registry, wires the arq queue, and drains executors on shutdown.
- `lru_cache` singletons in `deps.py` give clean dependency injection without a DI framework.

**Weaknesses**
- `AuthMiddleware` only exempts `/health`. `/ready` should also be public (load balancer probes don't carry API keys).
- `get_prediction_service()` in `deps.py` is not cached — creates a new instance per request. Harmless but inconsistent.
- `PredictAsyncBatchRequest.items` is typed as `list` (no item type, no min_length constraint), unlike `PredictBatchRequest` which uses `conlist`.

---

### Security (`security/`)

**Strengths**
- API key loading from env var with correct fallback to hardcoded dev keys.
- Scope enforcement is explicit and centralised in `permissions.py`.
- Dual-backend rate limiter: Redis sorted-set in production, in-process deque in dev. Same interface, transparent fallback.

**Weaknesses**
- `RedisRateLimiter.allow()` has a TOCTOU race. The pipeline does: remove stale → read count → add member → expire. The count check uses `count_before_add` which is correct in intent, but a concurrent request between `zcard` and `zadd` can slip through. A Lua script would make this atomic.
- API keys are loaded once at import time. `reload_keys()` exists for tests but there is no mechanism to rotate keys at runtime without a restart.

---

### Domain (`domain/`)

**Strengths**
- `InferencePipeline` (pre → validate → model → post) is the right abstraction. Pre/postprocessing are explicit, not hidden inside models.
- `ModelRegistry` is thread-safe with double-checked locking, LRU eviction via `OrderedDict`, hot-reload support, and auto-discovery from `models/`.
- `BaseModel`, `BasePreprocessor`, `BasePostprocessor`, `BaseValidator` are minimal, correct ABCs.

**Weaknesses**
- `_discover_definitions()` silently swallows all exceptions (`except Exception: pass`). A malformed or missing `definition.py` produces no output — no log, no warning.
- `run_batch()` on `InferencePipeline` is a sequential loop. There is no parallelism at the item level; the entire batch runs in a single executor thread.
- No upper bound on batch size in the request schema — a request with 100,000 items blocks an executor thread for its full duration.

---

### Execution (`execution/`)

**Strengths**
- `BaseExecutor` ABC with `submit()` and `submit_background()` makes custom executors trivial to add.
- `InferenceExecutor` correctly tracks inflight count and timeout count in Prometheus.
- `ExecutionPolicy` cleanly maps `model:version` → executor without the service layer knowing about executor types.
- ONNX and Triton executors are present and follow the same interface.

**Weaknesses**
- No circuit breaker. A model that consistently times out or errors will keep receiving requests with no backpressure.
- CPU executor hardcoded to 8 workers, GPU to 2, in `deps.py`. Should be configurable via env vars.

---

### Infrastructure (`infra/`)

**Strengths**
- `SQLiteJobStore` uses WAL mode, per-operation connections for thread safety, and a schema version table for migrations.
- `PostgresJobStore` uses `ThreadedConnectionPool` — correct for a sync service layer.
- arq worker correctly initialises its own registry and job store, shares the same database as the API server.
- Graceful fallback: no Redis → thread pool, no Postgres → SQLite. Both are transparent.

**Weaknesses**
- `PostgresJobStore` has no migration path beyond dropping and recreating the table. Fine for initial setup, fragile for schema changes in production.
- `asyncpg` is listed in `pyproject.toml` but not used anywhere. `PostgresJobStore` uses `psycopg2`.

---

### Observability (`core/`)

**Strengths**
- Prometheus metrics with correct label sets: `model`, `version`, `tenant` on request counters/histograms; `device` on executor gauges.
- Structured JSON logging with `request_id`, `job_id`, `model`, `version`, `tenant_id`, `latency_ms` on success paths.
- OpenTelemetry tracing with a no-op fallback — callers never need to guard against `ImportError`.
- SLA timeout system: per-model budgets with priority chain (explicit request → per-model SLA → global default).

**Weaknesses**
- Custom Prometheus `CollectorRegistry` in `metrics.py` means the default `/metrics` endpoint from `prometheus_client` won't include these metrics. The metrics route must use this registry explicitly (it does, but it's a footgun for anyone adding new metrics).

---

### Configuration (`config/`)

**Strengths**
- Routing strategies (static, canary, A/B) are cleanly separated from the service layer.
- A/B routing is deterministic on `identity_key` (SHA-256 hash) — same request ID always routes to the same version.
- SLA timeouts are a separate config file, not buried in service code.

**Weaknesses**
- All config is static Python dicts. Adding a model requires editing source files and restarting. No runtime config reload.

---

### Dependencies (`pyproject.toml`)

**Weaknesses**
- All dependencies use open lower-bound version ranges (`>=`). Should be pinned for reproducible production builds.
- `pytest` is in `[project.dependencies]` (runtime) instead of a dev dependency group.
- `asyncpg` is declared but unused.

---

## What's Missing for Full Production Readiness

| Gap | Impact |
|---|---|
| No Dockerfile for the engine itself | Can't containerise without writing one |
| No proper DB migration tooling | Schema changes in production are manual |
| No runtime config reload | Adding a model requires a restart |
| No batch item limit | Unbounded batch requests can starve the executor pool |
| No circuit breaker | Failing models keep receiving traffic |
| `/ready` requires auth | Load balancer health checks fail without an API key |
