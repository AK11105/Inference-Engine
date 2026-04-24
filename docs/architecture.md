# Architecture

## Overview

The Inference Engine is a **transport-independent, model-agnostic** serving backend. Its primary responsibility is orchestrating online inference — not training, not feature engineering, not experiment tracking.

The system is structured as a set of concentric layers, each with a single, well-defined responsibility.

---

## Architectural Invariants

These rules must never be violated as the system evolves:

### 1. Transport Independence
Core ML logic (`domain/`, `services/`, `execution/`) must not import FastAPI, Pydantic, or any HTTP concept. The `adapters/` layer is the only place where transport concerns live.

### 2. Model Ignorance
Models do not know where inputs come from, how outputs are used, or that they are served over HTTP. A model is a pure function: `input → output`.

### 3. Explicit Pipelines
Preprocessing and postprocessing are explicit, first-class components. There are no hidden transformations inside models.

### 4. Version Is First-Class
Every model is identified by `(name, version)`. The string `"latest"` is a routing decision, not a default behavior. Explicit versions always bypass routing.

---

## Layer Map

```
┌─────────────────────────────────────────────────────────┐
│  adapters/http          Transport Layer (FastAPI)        │
│  ├── routes/            HTTP route handlers              │
│  ├── schemas/           Pydantic request/response models │
│  ├── middleware/        Auth, rate limit, payload guard  │
│  └── deps.py            Dependency injection wiring      │
├─────────────────────────────────────────────────────────┤
│  services/              Use-Case Orchestration           │
│  ├── PredictionService  Sync inference orchestration     │
│  ├── AsyncInferenceService  Fire-and-forget wrapper      │
│  ├── RoutingService     Version resolution               │
│  └── JobService         Job lifecycle management         │
├─────────────────────────────────────────────────────────┤
│  execution/             Execution Control                │
│  ├── InferenceExecutor  ThreadPoolExecutor wrapper       │
│  └── ExecutionPolicy    Maps model:version → executor    │
├─────────────────────────────────────────────────────────┤
│  domain/                Core Domain                      │
│  ├── models/            BaseModel abstraction            │
│  ├── processing/        Pre/Postprocessor abstractions   │
│  ├── pipelines/         InferencePipeline composition    │
│  ├── registry/          ModelRegistry (lazy + cached)    │
│  ├── definitions/       Concrete pipeline factories      │
│  └── jobs/              Job entity + JobStore interface  │
├─────────────────────────────────────────────────────────┤
│  infra/                 Infrastructure Implementations   │
│  └── jobs/SQLiteJobStore  Persistent job storage         │
├─────────────────────────────────────────────────────────┤
│  core/                  Cross-Cutting Concerns           │
│  ├── metrics.py         Prometheus counters/histograms   │
│  └── logging.py         Structured JSON logging          │
├─────────────────────────────────────────────────────────┤
│  config/                Static Configuration             │
│  ├── routing.py         Version routing rules            │
│  └── execution.py       Executor assignment policy       │
├─────────────────────────────────────────────────────────┤
│  security/              Auth Domain Logic                │
│  ├── auth.py            API key → Identity resolution    │
│  ├── permissions.py     Scope enforcement                │
│  └── rate_limit.py      Sliding window rate limiter      │
└─────────────────────────────────────────────────────────┘
```

---

## Request Lifecycle

### Synchronous Inference (`POST /predict`)

```
1. HTTP request arrives
2. PayloadGuardMiddleware  → reject if body > 1MB
3. RateLimitMiddleware     → reject if rate exceeded
4. AuthMiddleware          → resolve API key → Identity
5. Route handler           → validate request schema
6. require_scope()         → enforce "predict" scope
7. PredictionService.predict()
   a. RoutingService.resolve()  → determine (model, version)
   b. JobService.create_job()   → persist CREATED → PENDING
   c. ExecutionPolicy.resolve() → select executor (cpu/gpu)
   d. ModelRegistry.get()       → load/cache InferencePipeline
   e. executor.submit()         → run in thread pool
      i.  JobService.mark_running()
      ii. pipeline.run(payload)
          - preprocessor.transform(raw_input)
          - model.predict(model_input)
          - postprocessor.transform(model_output)
      iii. JobService.mark_succeeded(result)
   f. Metrics: increment request counter, record latency
8. Return PredictResponse
```

### Asynchronous Inference (`POST /predict/async`)

```
1–6. Same as synchronous (auth, rate limit, scope)
7. AsyncInferenceService.submit()
   a. JobService.create_job()   → persist CREATED → PENDING
   b. ExecutionPolicy.resolve() → select executor
   c. executor.submit_background(run) → fire and forget
8. Return PredictAsyncResponse { job_id }
9. Client polls GET /predict/async/{job_id}
```

---

## Concurrency Model

The `InferenceExecutor` wraps Python's `ThreadPoolExecutor`. Each executor instance is bound to a logical device (`cpu` or `gpu`) and has a configurable `max_workers`.

- **Sync inference**: `executor.submit(fn, timeout_s=...)` — blocks until result or timeout
- **Async inference**: `executor.submit_background(fn)` — fire-and-forget, no result awaited
- **Batch inference**: `executor.submit_batch(fn)` — same as submit, batch semantics belong to the pipeline

The `ExecutionPolicy` maps `model:version` keys to named executors, allowing different models to run on different hardware pools.

---

## Dependency Injection

All service wiring happens in `app/adapters/http/deps.py`. FastAPI's `Depends()` mechanism is used at the route level. Singletons are created with `@lru_cache`.

Key singletons (one per process):
- `ModelRegistry` — shared pipeline cache
- `InferenceExecutor` (cpu) — shared thread pool for CPU workloads
- `InferenceExecutor` (gpu) — shared thread pool for GPU workloads
- `RoutingService` — stateless, shared
- `ExecutionPolicy` — stateless, shared
- `SQLiteJobStore` — single connection, `check_same_thread=False`

---

## Folder Responsibilities (Frozen)

| Folder | Owns |
|---|---|
| `domain/models/` | Model abstraction only |
| `domain/processing/` | Pre/postprocessor abstractions only |
| `domain/pipelines/` | Pipeline composition only |
| `domain/registry/` | Pipeline loading and caching only |
| `domain/definitions/` | Concrete pipeline factory functions |
| `domain/jobs/` | Job entity, status enum, store interface |
| `services/` | Use-case orchestration (no HTTP, no infra) |
| `execution/` | Thread pool management, timeout, policy |
| `adapters/http/` | FastAPI routes, schemas, middleware |
| `infra/` | Concrete infrastructure (SQLite, etc.) |
| `core/` | Metrics, logging (no business logic) |
| `config/` | Static configuration values |
| `security/` | Auth domain logic (no HTTP) |

Folder responsibilities must not overlap.
