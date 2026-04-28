# Request Flow

## Synchronous inference

```
POST /predict
  │
  ├─ AuthMiddleware          validates X-API-Key → attaches Identity to request.state
  ├─ RateLimitMiddleware     checks per-tenant sliding window
  ├─ PayloadGuardMiddleware  rejects bodies > 1 MB
  │
  ├─ predict route           parses PredictRequest, calls PredictionService.predict()
  │
  └─ PredictionService
      ├─ RoutingService.resolve()      → (model, version)
      ├─ JobService.create_job()       → job_id  (status: PENDING)
      ├─ ExecutionPolicy.resolve()     → executor
      ├─ _resolve_timeout()            → effective timeout (request > SLA > global default)
      ├─ tracer.start_as_current_span() → OTel span with model/version/tenant attributes
      ├─ ModelRegistry.get()           → pipeline  (LRU cache; evicts if max_loaded exceeded)
      └─ executor.submit(run, timeout_s=effective_timeout)
          ├─ JobService.mark_running()
          ├─ pipeline.run(payload)
          │   ├─ preprocessor.transform()
          │   ├─ validator.validate()
          │   ├─ model.predict()
          │   └─ postprocessor.transform()
          └─ JobService.mark_succeeded() / mark_failed()
```

Returns `{"result": ...}` to the client.

---

## Asynchronous inference

```
POST /predict/async
  │
  ├─ (same middleware stack)
  │
  └─ AsyncInferenceService.submit()
      ├─ JobService.create_job()       → job_id  (status: PENDING)
      │
      ├─ [Redis available]
      │   └─ ArqJobQueue.enqueue_inference(job_id, ...)
      │       └─ arq worker (separate process):
      │           ├─ mark_running()
      │           ├─ pipeline.run(payload)
      │           └─ mark_succeeded() / mark_failed()
      │
      └─ [No Redis]
          └─ executor.submit_background(run)   ← fire-and-forget, same process

Returns {"job_id": "..."} immediately.
```

```
GET /predict/async/{job_id}
  └─ JobService.get_job(job_id) → Job → PredictAsyncStatusResponse
```

---

## Admin hot-reload

```
POST /admin/models/{name}/{version}/reload
  │
  ├─ AuthMiddleware + require_scope("admin")
  │
  └─ ModelRegistry.reload(name, version)
      ├─ Acquires per-key lock
      ├─ Evicts cached pipeline
      ├─ Calls build_pipeline() fresh
      └─ Stores new pipeline in LRU cache
```

In-flight requests using the old pipeline complete normally. Subsequent requests get the new one.

---

## Graceful shutdown

```
Lifespan shutdown
  ├─ cpu_executor._executor.shutdown(wait=True)   ← drains all in-flight futures
  ├─ gpu_executor._executor.shutdown(wait=True)
  └─ lru_cache cleared for all dep singletons     ← fresh state on next startup
```

---

## Middleware execution order

Middleware runs in reverse registration order in Starlette. Effective order per request:

```
AuthMiddleware  →  RateLimitMiddleware  →  PayloadGuardMiddleware  →  Route handler
```

A request that fails auth never reaches the rate limiter. A request that fails the rate limiter never reaches the route handler.
