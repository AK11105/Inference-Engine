# Architecture Overview

## Layers

The engine is split into four layers. Each layer only depends on the layer below it — never above.

```
HTTP Adapter  (FastAPI routes, middleware, schemas)
     ↓
Service Layer (orchestration, business logic)
     ↓
Domain Layer  (models, pipelines, registry, jobs)
     ↓
Infrastructure (job stores, queue, loaders)
```

The execution layer is injected into the service layer via `ExecutionPolicy` — it is a pluggable runtime concern, not a separate tier.

---

## Layer responsibilities

| Layer | Package | Knows about |
|---|---|---|
| HTTP Adapter | `app/adapters/http/` | FastAPI, Pydantic, HTTP status codes |
| Service | `app/services/` | Domain objects, executors, metrics, logging |
| Domain | `app/domain/` | Pure Python — no HTTP, no storage SDKs |
| Infrastructure | `app/infra/` | psycopg2, arq, boto3 |
| Execution | `app/execution/` | ThreadPoolExecutor, onnxruntime, tritonclient |
| Config | `app/config/` | Routing rules, executor assignments, SLA timeouts |

---

## Invariants

These rules must never be broken:

1. **No upward imports.** Domain never imports from services or adapters. Services never import from adapters.
2. **No HTTP in domain or services.** `fastapi`, `starlette`, `pydantic` are adapter-layer concerns only.
3. **No storage SDKs in domain.** `psycopg2`, `boto3`, `arq` belong in `infra/` only.
4. **Explicit pipeline stages.** Pre/postprocessing are separate classes, never hidden inside `model.predict()`.
5. **Every request creates a job.** Sync and async paths both write a `Job` record — full audit trail.
6. **Version is always explicit at execution time.** Routing resolves `None` to a concrete version before any pipeline is touched.

---

## Dependency injection

All shared singletons (registry, executors, services, job store) are constructed once via `@lru_cache` providers in `app/adapters/http/deps.py` and wired into route handlers via FastAPI's `Depends()`.

The lifespan hook in `app/adapters/http/app.py` runs at startup to warm up all pipelines and connect the arq queue if `REDIS_URL` is set — so the first request never pays the model loading cost. On shutdown it drains all in-flight executor threads before the process exits and clears cached singletons so a subsequent startup gets fresh instances.
