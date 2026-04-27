# Project Assessment & Roadmap

**Assessed:** 2026-04-24  
**Updated:** 2026-04-27  
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

### 1. ✅ SQLite for job persistence — hard blocker for scale
~~Single connection, `check_same_thread=False`, no connection pooling. Will corrupt under concurrent async writes.~~

**Done.** `SQLiteJobStore` uses WAL mode, per-operation connections, and a `threading.Lock`. `PostgresJobStore` (psycopg2 `ThreadedConnectionPool`, min 1 / max 10) is used automatically when `DATABASE_URL` is set. The `JobStore` interface is abstract — only the infra layer changed.

### 2. ✅ In-memory rate limiter — broken in any real deployment
~~Per-process state means rate limits don't work behind a load balancer or with multiple workers.~~

**Done.** `RedisRateLimiter` uses a Redis sorted set (`ZADD` / `ZREMRANGEBYSCORE`) and is selected automatically when `REDIS_URL` is set. Falls back to in-process `RateLimiter` when Redis is absent.

### 3. ✅ In-memory API key store — not a real auth system
~~`API_KEYS` dict in source code. No rotation, no expiry, no revocation, keys in plaintext.~~

**Done.** Keys are loaded from the `API_KEYS` environment variable at startup (`key:tenant_id:scope1,scope2` format). Hardcoded dev keys are fallback-only and documented as unsafe for production. `reload_keys()` is available for test isolation.

### 4. ✅ `ModelRegistry` is not thread-safe
~~Two concurrent requests for the same unloaded model will both call `build_pipeline()` simultaneously.~~

**Done.** Each `(name, version)` key has its own `threading.Lock` in `_locks`. The double-checked locking pattern is used: check cache → acquire lock → check cache again → build.

### 5. ✅ Bare `except:` in `ExecutionPolicy`
~~Catches `KeyboardInterrupt`, `SystemExit`, everything.~~

**Done.** `ExecutionPolicy.resolve()` uses `except KeyError` and raises `RuntimeError` with a descriptive message.

### 6. ✅ No model warm-up at startup
~~Models are lazy-loaded on first request. First caller gets cold-start latency.~~

**Done.** `registry.warm_up()` is called in the FastAPI lifespan hook (`app.py`). All pipelines are loaded before the server accepts traffic.

---

## What's Missing for a "Big, Reusable, General" Project

| Gap | Status | Notes |
|---|---|---|
| No async I/O | ⚠️ Partial | `ThreadPoolExecutor` still used; async endpoints exist but service layer is sync |
| No model artifact storage | ✅ Done | `ModelLoader` interface + `LocalModelLoader` + `S3ModelLoader` implemented |
| `/ready` is a lie | ✅ Done | `registry.is_ready()` checks all pipelines are loaded; returns `503` until warm-up completes |
| No semantic input validation | ✅ Done | `BaseValidator` / `NoOpValidator` hook in pipeline; `ValidationError` → HTTP 400 |
| No batching queue | ✅ Done | arq + Redis queue with `run_inference` / `run_batch_inference` worker tasks; falls back to thread pool |
| No timeout on async jobs | ✅ Done | `WorkerSettings.job_timeout = 300`; executor `timeout_s` propagated through service layer |
| `tenant_id` is unused | ✅ Done | Applied to Prometheus labels (`model`, `version`, `tenant`), rate limit keys, and job records |
| No model unloading | ❌ Open | Pipelines live forever; no LRU eviction or memory pressure handling |

---

## Architecture Upgrades for Real Scale

**Replace `ThreadPoolExecutor` with a proper task queue** — ✅ Done  
arq + Redis queue implemented. Jobs are persisted in the job store — if the API process dies, jobs can be recovered. Worker runs as a separate process.

**Add a plugin/discovery system for models** — ✅ Done  
`ModelRegistry` auto-discovers `models/<name>/<version>/definition.py` at startup. No registry code changes needed to add a model.

**Separate the model server from the API server** — ❌ Open  
Still a single process. Triton executor exists as a client but the split is not enforced.

**Pluggable executor backends** — ✅ Done  
`BaseExecutor` interface + `InferenceExecutor` (ThreadPool), `OnnxExecutor` (ONNX Runtime), `TritonExecutor` (Triton gRPC). `ExecutionPolicy` maps `model:version` to executor at runtime.

---

## Prioritized Roadmap

### Phase 1 — Fix what's broken ✅ Complete
1. ✅ Thread-safe registry loading (per-key lock + double-checked locking)
2. ✅ Fix bare `except:` in `ExecutionPolicy`
3. ✅ Model warm-up at startup via lifespan hook
4. ✅ `/ready` endpoint checks actual registry state

### Phase 2 — Make it deployable ✅ Complete
5. ✅ PostgreSQL `JobStore` (psycopg2 connection pool, auto-schema)
6. ✅ Redis rate limiter (sorted set, cross-process accurate)
7. ✅ Environment-variable-based API key config (`API_KEYS` env var)
8. ✅ Proper async job queue (arq + Redis, with in-process fallback)

### Phase 3 — Make it general and reusable ✅ Complete
9. ✅ Model artifact store abstraction (`ModelLoader`, `LocalModelLoader`, `S3ModelLoader`)
10. ✅ Auto-discovery of pipeline definitions from `models/` directory
11. ✅ Per-tenant metrics, rate limits, and job isolation
12. ✅ Plugin interface for executors (Triton, ONNX Runtime, custom)
13. ✅ Input validation hooks in the pipeline (`BaseValidator`, `ValidationError`)

### Phase 4 — Make it production-grade ❌ Open
14. ❌ Distributed tracing (OpenTelemetry)
15. ❌ Model memory management (LRU eviction, memory pressure callbacks)
16. ❌ Graceful shutdown (drain in-flight requests, persist pending jobs)
17. ❌ Admin API for hot-reloading models without restart
18. ❌ SLA/timeout budgets per model, not just per request

---

## Bottom Line

Phases 1–3 are complete. The project has moved from "correct architecture sketch" to a deployable, general-purpose inference platform. The remaining gap is Phase 4 — production hardening: tracing, memory management, graceful shutdown, and hot-reload. These require depth, not new abstractions.
