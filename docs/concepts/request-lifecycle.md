# Request Lifecycle

## Synchronous inference

![Synchronous request lifecycle sequence diagram](../assets/sync-request-lifecycle-light.png#only-light)
![Synchronous request lifecycle sequence diagram](../assets/sync-request-lifecycle-dark.png#only-dark)

Returns `{"result": ...}` to the client.

---

## Asynchronous inference

![Asynchronous request lifecycle sequence diagram](../assets/async-request-lifecycle-light.png#only-light)
![Asynchronous request lifecycle sequence diagram](../assets/async-request-lifecycle-dark.png#only-dark)

```
GET /predict/async/{job_id}
  └─ JobService.get_job(job_id) → Job → PredictAsyncStatusResponse
```

---

## Middleware execution order

Middleware runs in reverse registration order in Starlette. Effective order per request:

```
AuthMiddleware  →  RateLimitMiddleware  →  PayloadGuardMiddleware  →  Route handler
```

A request that fails auth never reaches the rate limiter.

---

## Graceful shutdown

```
Lifespan shutdown
  ├─ cpu_executor._executor.shutdown(wait=True)   ← drains all in-flight futures
  ├─ gpu_executor._executor.shutdown(wait=True)
  └─ lru_cache cleared for all dep singletons
```
