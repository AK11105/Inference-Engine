# Project Assessment & Roadmap

**Assessed:** 2026-04-24  
**Overall Rating: 6.5 / 10** — Solid architectural thinking, weak execution depth.

The abstractions are correct and the invariants are well-reasoned. The implementation is thin in almost every layer that matters for production scale.

---

## What's Actually Good (Don't Touch)

- **Layer separation is correct.** Transport → Services → Domain → Infra is the right shape.
- **Version as first-class citizen.** `(name, version)` as the registry key is correct.
- **Explicit pipelines.** Pre/post as first-class components, not hidden inside models.
- **Job abstraction exists.** Most hobby inference servers don't have this at all.
- **Routing strategies are real.** Canary + A/B + static is a legitimate set.
- **Prometheus metrics are scoped correctly.** Per-model, per-version, per-device labels are the right granularity.

---

## What's Broken or Dangerous Right Now

### 1. SQLite for job persistence — hard blocker for scale
Single connection, `check_same_thread=False`, no connection pooling. Will corrupt under concurrent async writes.

**Fix:** PostgreSQL via `asyncpg` or SQLAlchemy async. The `JobStore` interface is already abstract — only the infra layer changes.

### 2. In-memory rate limiter — broken in any real deployment
Per-process state means rate limits don't work behind a load balancer or with multiple workers. Two Uvicorn workers = double the effective rate limit.

**Fix:** Redis-backed sliding window.

### 3. In-memory API key store — not a real auth system
`API_KEYS` dict in source code. No rotation, no expiry, no revocation, keys in plaintext.

**Fix:** Environment variable injection at minimum. Properly: secrets manager or DB-backed key store with hashed keys.

### 4. `ModelRegistry` is not thread-safe
Two concurrent requests for the same unloaded model will both call `build_pipeline()` simultaneously — race condition on the lazy-load path.

```python
# Race condition:
if key in self._pipelines:
    return self._pipelines[key]
# ← another thread can enter here simultaneously
pipeline = self._definitions[key]()
self._pipelines[key] = pipeline
```

**Fix:** `threading.Lock()` per key, or load all pipelines eagerly at startup.

### 5. Bare `except:` in `ExecutionPolicy`
Catches `KeyboardInterrupt`, `SystemExit`, everything. Use `except KeyError`.

### 6. No model warm-up at startup
Models are lazy-loaded on first request. First caller gets cold-start latency. Models should load at startup.

---

## What's Missing for a "Big, Reusable, General" Project

| Gap | Why it matters |
|---|---|
| No async I/O | Entire service layer is sync. `ThreadPoolExecutor` is a workaround, not a solution. |
| No model artifact storage | Models are hardcoded in definitions. A real system needs S3/GCS/MLflow and a `ModelLoader` interface. |
| `/ready` is a lie | Always returns `ready` regardless of whether models are actually loaded. |
| No semantic input validation | Pydantic validates structure, not shape/dtype/range. No validation hooks in the pipeline. |
| No batching queue | Async jobs fire into a thread pool with no queue, no backpressure, no retry. Jobs silently drop under load. |
| No timeout on async jobs | `submit_background` has no timeout. A hung model holds a thread forever. |
| `tenant_id` is unused | It's on `Identity` but never applied to metrics, rate limits, or job isolation. |
| No model unloading | Once loaded, pipelines live forever. No LRU eviction, no memory pressure handling. |

---

## Architecture Upgrades for Real Scale

**Replace `ThreadPoolExecutor` with a proper task queue**  
For async inference at scale: Celery + Redis/RabbitMQ, or `arq`/`dramatiq`. The current approach has no persistence — if the process dies, in-flight async jobs are lost.

**Add a plugin/discovery system for models**  
Adding a model currently requires editing `registry.py`. A production system should auto-discover definition modules from a directory:

```
models/
  sentiment/v1/definition.py
  classifier/v2/definition.py
```

**Separate the model server from the API server**  
For GPU workloads, the inference executor should be a separate process/service. This allows independent scaling of API capacity vs. compute capacity.

**Pluggable executor backends**  
Current executor is `ThreadPoolExecutor` only. A general system needs: `ProcessPoolExecutor` for CPU-bound models, Triton client for GPU serving, ONNX Runtime for optimized inference.

---

## Prioritized Roadmap

### Phase 1 — Fix what's broken
1. Thread-safe registry loading (lock or eager startup)
2. Fix bare `except:` in `ExecutionPolicy`
3. Model warm-up at startup, not on first request
4. `/ready` endpoint that actually checks model state

### Phase 2 — Make it deployable
5. PostgreSQL `JobStore` (swap infra, interface unchanged)
6. Redis rate limiter (swap security layer)
7. Environment-variable-based API key config
8. Proper async job queue (arq or Celery) replacing `submit_background`

### Phase 3 — Make it general and reusable
9. Model artifact store abstraction (S3/GCS/local) with a `ModelLoader` interface
10. Auto-discovery of pipeline definitions from a directory
11. Per-tenant metrics, rate limits, and job isolation
12. Plugin interface for executors (Triton, ONNX Runtime, torch.compile, etc.)
13. Input validation hooks in the pipeline (shape, dtype, range)

### Phase 4 — Make it production-grade
14. Distributed tracing (OpenTelemetry)
15. Model memory management (LRU eviction, memory pressure callbacks)
16. Graceful shutdown (drain in-flight requests, persist pending jobs)
17. Admin API for hot-reloading models without restart
18. SLA/timeout budgets per model, not just per request

---

## Bottom Line

The project has the right bones. The abstractions — pipeline, registry, executor, routing — are correct and would survive a real production system. What's missing is depth: the implementations are stubs where they need to be robust, and entire subsystems (artifact storage, queue, multi-tenancy) are absent.

The gap between "correct architecture sketch" and "general, reusable ML serving platform" is roughly 3–4x the current codebase in the right places. The architecture won't need to be torn down — it needs to be filled in.
