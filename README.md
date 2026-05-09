# Inference Engine

A production-grade, task-agnostic ML inference backend. Serve any trained model — PyTorch, sklearn, ONNX, or anything else — over HTTP without changing the engine's core.

---

## What it does

The engine provides a clean execution layer between your trained model artifacts and the outside world. You plug in a model; the engine handles routing, execution, job tracking, rate limiting, auth, and observability.

It does **not** train models, track experiments, or manage feature pipelines. It consumes trained artifacts and serves them.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Core Concepts](#core-concepts)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Adding a Model](#adding-a-model)
- [Async Inference & Job Queue](#async-inference--job-queue)
- [Security](#security)
- [Observability](#observability)
- [Execution Backends](#execution-backends)
- [Routing Strategies](#routing-strategies)
- [Storage Backends](#storage-backends)
- [Running Tests](#running-tests)

---

## Architecture

```
Client Request
      │
      ▼
┌─────────────────────────────────────────┐
│           HTTP Adapter (FastAPI)        │
│  AuthMiddleware → RateLimit → Payload   │
│  Routes: /predict, /predict/batch,      │
│          /predict/async, /jobs, ...     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│           Service Layer                 │
│  PredictionService  AsyncInferenceService│
│  RoutingService     JobService          │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│           Domain Layer                  │
│  ModelRegistry → InferencePipeline      │
│  Preprocessor → Validator → Model       │
│                           → Postprocessor│
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│           Execution Layer               │
│  ExecutionPolicy → InferenceExecutor    │
│  (ThreadPool / ONNX / Triton)           │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│           Infrastructure                │
│  JobStore (SQLite / Postgres)           │
│  Queue (arq + Redis)                   │
│  Loader (Local / S3)                   │
└─────────────────────────────────────────┘
```

**Key invariants that must never be violated:**

1. Core ML logic never imports FastAPI, Pydantic, or HTTP concepts.
2. Models do not know where inputs come from or how outputs are used.
3. Pre/postprocessing are explicit, first-class components — no hidden transforms inside models.
4. Every model is identified by `(name, version)`. "latest" is a routing decision, not a default.

---

## Project Structure

```
inference_engine/
├── app/
│   ├── adapters/
│   │   └── http/
│   │       ├── app.py              # FastAPI app factory + lifespan
│   │       ├── deps.py             # Dependency injection providers
│   │       ├── middleware/
│   │       │   ├── auth.py         # API key authentication middleware
│   │       │   ├── rate_limit.py   # Sliding-window rate limiter middleware
│   │       │   └── payload_guard.py# 1 MB payload size guard
│   │       ├── routes/
│   │       │   ├── predict.py      # POST /predict
│   │       │   ├── predict_batch.py# POST /predict/batch
│   │       │   ├── predict_async.py# POST /predict/async, GET /predict/async/{id}
│   │       │   ├── predict_async_batch.py
│   │       │   ├── jobs.py         # GET /jobs/{id}
│   │       │   ├── models.py       # GET /models
│   │       │   ├── metrics.py      # GET /metrics (Prometheus)
│   │       │   ├── health.py       # GET /health
│   │       │   ├── ready.py        # GET /ready
│   │       │   └── debug.py        # GET /debug/models/loaded
│   │       └── schemas/
│   │           ├── request.py      # Pydantic request models
│   │           └── response.py     # Pydantic response models
│   ├── config/
│   │   ├── routing.py              # Model routing rules (canary, A/B, static)
│   │   └── execution.py            # Executor assignment per model:version
│   ├── core/
│   │   ├── logging.py              # JSON structured logging setup
│   │   └── metrics.py              # Prometheus counters, histograms, gauges
│   ├── domain/
│   │   ├── definitions/            # Built-in model pipeline definitions
│   │   │   ├── echo_v1.py
│   │   │   └── echo_v2.py
│   │   ├── jobs/                   # Job domain model
│   │   │   ├── job.py              # Job dataclass
│   │   │   ├── job_state.py        # JobStatus enum
│   │   │   └── job_store.py        # Abstract JobStore interface
│   │   ├── loading/                # Artifact loader abstractions
│   │   │   ├── base.py             # ModelLoader ABC
│   │   │   ├── local_loader.py     # Load from local filesystem
│   │   │   └── s3_loader.py        # Download from S3
│   │   ├── models/
│   │   │   ├── base.py             # BaseModel ABC
│   │   │   └── echo_model.py       # EchoModel (identity, for testing)
│   │   ├── pipelines/
│   │   │   └── base.py             # InferencePipeline (pre → validate → model → post)
│   │   ├── processing/
│   │   │   ├── pre.py              # BasePreprocessor + IdentityPreprocessor
│   │   │   └── post.py             # BasePostprocessor + IdentityPostprocessor
│   │   ├── registry/
│   │   │   └── registry.py         # ModelRegistry (lazy load, thread-safe cache)
│   │   └── validation/
│   │       └── base.py             # BaseValidator + NoOpValidator
│   ├── execution/
│   │   ├── base.py                 # BaseExecutor ABC
│   │   ├── executor.py             # InferenceExecutor (ThreadPoolExecutor)
│   │   ├── execution_policy.py     # ExecutionPolicy (model → executor routing)
│   │   ├── onnx_executor.py        # ONNX Runtime executor
│   │   └── triton_executor.py      # Triton Inference Server executor
│   ├── infra/
│   │   ├── jobs/
│   │   │   ├── sqlite_job_store.py # SQLite-backed JobStore (default)
│   │   │   └── postgres_job_store.py# PostgreSQL-backed JobStore
│   │   └── queue/
│   │       ├── queue.py            # arq Redis queue client
│   │       └── worker.py           # arq worker tasks + WorkerSettings
│   ├── security/
│   │   ├── auth.py                 # API key loading + Identity
│   │   ├── permissions.py          # Scope enforcement
│   │   └── rate_limit.py           # RateLimiter + RedisRateLimiter
│   └── services/
│       ├── prediction_service.py   # Sync inference orchestration
│       ├── async_inference_service.py # Async job submission
│       ├── job_service.py          # Job lifecycle management
│       └── routing_service.py      # Version resolution
├── tests/
│   ├── test_phase1.py
│   ├── test_phase2.py
│   └── test_phase3.py
├── docs/
├── docker-compose.yml              # Postgres + Redis for local dev
├── dev.sh                          # One-command local dev startup
├── pyproject.toml
└── .env.example
```

---

## Core Concepts

| Term | What it is |
|---|---|
| **Model** | Pure inference logic. Implements `load()` and `predict()`. Knows nothing about HTTP or storage. |
| **Preprocessor** | Transforms raw external input into model-ready input. |
| **Postprocessor** | Transforms model output into a response-ready format. |
| **Validator** | Runs after preprocessing, before inference. Checks shape, dtype, value ranges. Optional. |
| **Pipeline** | Composes Preprocessor → Validator → Model → Postprocessor into a single `run()` call. |
| **Registry** | Loads, caches, and serves pipelines by `(name, version)`. Thread-safe, lazy-loading. |
| **RoutingService** | Resolves a `(model, requested_version)` pair to a concrete `(model, version)` using canary, A/B, or static rules. |
| **ExecutionPolicy** | Maps `model:version` to an executor (CPU thread pool, ONNX, Triton). |
| **Executor** | Runs a callable in a thread pool with timeout and metrics. |
| **Job** | A record of a single inference request with status, result, and error tracking. |
| **JobStore** | Persists jobs. SQLite by default; Postgres when `DATABASE_URL` is set. |
| **Queue** | arq + Redis for async job dispatch. Falls back to thread pool when Redis is absent. |

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker (for Postgres + Redis in full mode)

### Minimal local run (no Redis, no Postgres)

```bash
# 1. Clone and install
git clone <repo>
cd inference-engine
uv sync          # or: pip install -e .

# 2. Start the server
uvicorn app.adapters.http.app:app --reload

# 3. Test it
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# → {"result": "hello"}
```

The server starts with SQLite for job storage and an in-process thread pool for async jobs. No external dependencies required.

### Full local run (Postgres + Redis + arq worker)

```bash
# 1. Copy and edit env
cp .env.example .env

# 2. Start everything (infra + worker + server)
bash dev.sh
```

`dev.sh` starts Docker services, waits for them to be healthy, runs the DB migration, launches the arq worker, and starts uvicorn — all in one command.

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | dev/admin hardcoded keys | Semicolon-separated list of `key:tenant_id:scope1,scope2` entries |
| `DATABASE_URL` | *(unset — uses SQLite)* | PostgreSQL DSN: `postgresql://user:pass@host/db` |
| `REDIS_URL` | *(unset — uses thread pool)* | Redis DSN: `redis://localhost:6379/0` |

**API_KEYS format:**
```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

**Fallback behaviour:** When `DATABASE_URL` is not set, the engine uses SQLite at `app/instance/jobs.db`. When `REDIS_URL` is not set, async jobs run in the local thread pool. Both fallbacks are transparent — no code changes needed.

### Routing configuration (`app/config/routing.py`)

Controls how version is resolved when a client does not specify one:

```python
ROUTES = {
    "echo": {
        "strategy": "canary",
        "primary": "v1",
        "canary": "v2",
        "canary_percent": 50,   # 50% of traffic goes to v2
    },
    "classifier": {
        "strategy": "ab",
        "variants": {"v1": 50, "v2": 50},  # weights, must sum to 100
    },
    "stable_model": {
        "strategy": "static",
        "version": "v3",
    },
}
```

### Execution policy (`app/config/execution.py`)

Controls which executor handles each model version:

```python
EXECUTION_POLICY = {
    "echo:v1": "gpu",
    "echo:v2": "cpu",
}
DEFAULT_EXECUTOR = "cpu"
```

---

## API Reference

All endpoints except `/health` require the `X-API-Key` header.

### Authentication

```
X-API-Key: <your-api-key>
```

Available scopes: `predict`, `read_models`, `admin`.

---

### POST /predict

Synchronous single inference. Blocks until the result is ready.

**Required scope:** `predict`

**Request:**
```json
{
  "model": "echo",
  "version": "v1",   // optional — omit to use routing rules
  "data": <any JSON value>
}
```

**Response `200`:**
```json
{"result": <any JSON value>}
```

**Errors:** `400` model/input error, `500` execution error.

---

### POST /predict/batch

Synchronous batch inference. Runs all items through the same model.

**Required scope:** `predict`

**Request:**
```json
{
  "model": "echo",
  "version": "v1",
  "items": [<item1>, <item2>, ...]   // min 1 item
}
```

**Response `200`:**
```json
{"results": [<result1>, <result2>, ...]}
```

---

### POST /predict/async

Submit an inference job and return immediately with a job ID.

**Required scope:** `predict`

**Request:**
```json
{
  "model": "echo",
  "version": "v1",
  "data": <any JSON value>
}
```

**Response `200`:**
```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000"}
```

---

### GET /predict/async/{job_id}

Poll the status of an async job.

**Required scope:** `predict`

**Response `200`:**
```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",       // created | pending | running | succeeded | failed | cancelled
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-27T15:00:00Z",
  "result": <value or null>,
  "error_message": <string or null>
}
```

**Errors:** `404` job not found.

---

### POST /predict/async/batch

Submit a batch inference job asynchronously.

**Required scope:** `predict`

**Request:**
```json
{
  "model": "echo",
  "version": "v1",
  "items": [<item1>, <item2>, ...]
}
```

**Response `200`:**
```json
{"job_id": "550e8400-..."}
```

---

### GET /jobs/{job_id}

Retrieve a job record directly from the job store.

**Response `200`:**
```json
{
  "job_id": "550e8400-...",
  "status": "succeeded",
  "model": "echo",
  "version": "v1",
  "created_at": "2026-04-27T15:00:00Z"
}
```

---

### GET /models

List all registered models and versions.

**Required scope:** `read_models`

**Response `200`:**
```json
{"models": [{"name": "echo", "version": "v1"}, {"name": "echo", "version": "v2"}]}
```

---

### GET /health

Liveness check. No authentication required.

**Response `200`:** `{"status": "ok"}`

---

### GET /ready

Readiness check. Returns `503` while models are still loading.

**Response `200`:** `{"status": "ready"}`
**Response `503`:** `{"status": "loading"}`

---

### GET /metrics

Prometheus metrics in text format.

**Required scope:** `admin`

---

### GET /debug/models/loaded

Lists models currently loaded in memory (warm cache).

**Required scope:** `admin`

---

## Adding a Model

A model is a Python module that exposes three things: `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()`. The registry discovers it automatically.

### Directory layout

Two separate directories are involved — they serve different purposes:

```
models/
└── my_model/
    └── v1/
        └── definition.py       ← registry entry point (auto-discovered)

model_artifacts/
└── my_model/
    └── v1/
        └── model.pkl           ← artifact file, loaded inside definition.py
```

`models/` contains Python code. `model_artifacts/` contains binary artifacts (weights, pickles, ONNX files, etc.). The registry scans `models/` at startup; `model_artifacts/` is just a filesystem convention used by `LocalModelLoader` inside your `build_pipeline()` function.

### Step 1 — Implement the model

```python
# app/domain/models/my_model.py
from app.domain.models.base import BaseModel

class MyModel(BaseModel):
    def load(self) -> None:
        # Load weights, initialize runtime, etc.
        import joblib
        self._clf = joblib.load("model_artifacts/my_model/v1/model.pkl")

    def predict(self, x):
        return self._clf.predict([x])[0]
```

### Step 2 — Implement pre/postprocessors (if needed)

```python
# app/domain/processing/pre.py (or a new file)
from app.domain.processing.pre import BasePreprocessor

class MyPreprocessor(BasePreprocessor):
    def transform(self, raw_input):
        # Convert raw JSON input to model-ready format
        return [float(v) for v in raw_input["features"]]
```

Use `IdentityPreprocessor` / `IdentityPostprocessor` if no transformation is needed.

### Step 3 — Write the pipeline definition

```python
# app/domain/definitions/my_model_v1.py
from app.domain.models.my_model import MyModel
from app.domain.processing.pre import MyPreprocessor
from app.domain.processing.post import IdentityPostprocessor
from app.domain.pipelines.base import InferencePipeline

MODEL_NAME = "my_model"
MODEL_VERSION = "v1"

def build_pipeline() -> InferencePipeline:
    model = MyModel()
    model.load()
    return InferencePipeline(
        preprocessor=MyPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
```

### Step 4 — Register it

**Option A — Built-in (hardcoded):** Add the import to `app/domain/registry/registry.py` in `_definitions`:

```python
from app.domain.definitions import my_model_v1

self._definitions = {
    ...
    (my_model_v1.MODEL_NAME, my_model_v1.MODEL_VERSION): my_model_v1.build_pipeline,
}
```

**Option B — Auto-discovery:** Place a `definition.py` file under `models/<model_name>/<version>/definition.py`. The registry scans this directory at startup and loads any file that exposes `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()`.

```
models/
└── my_model/
    └── v1/
        └── definition.py   ← same structure as Step 3
```

### Step 5 — Add routing (optional)

If you want version routing without clients specifying a version explicitly, add an entry to `app/config/routing.py`:

```python
ROUTES = {
    "my_model": {
        "strategy": "static",
        "version": "v1",
    },
}
```

### Step 6 — Test it

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "my_model", "version": "v1", "data": {"features": [1.0, 2.0, 3.0]}}'
```

---

## Async Inference & Job Queue

Every inference request — sync or async — creates a `Job` record in the job store. This gives you a full audit trail regardless of execution mode.

### How async works

```
POST /predict/async
      │
      ▼
AsyncInferenceService.submit()
      │
      ├── creates Job record (status: PENDING)
      │
      ├── if Redis available → enqueues to arq
      │                         arq worker picks it up
      │
      └── if no Redis → submits to thread pool immediately
                        (fire-and-forget, same process)

GET /predict/async/{job_id}
      │
      └── reads Job from store → returns current status + result
```

### Running the arq worker

```bash
arq app.infra.queue.worker.WorkerSettings
```

The worker initialises its own `ModelRegistry` and `JobService` at startup. It shares the same job store as the API server (both read/write the same database).

### Job lifecycle

```
CREATED → PENDING → RUNNING → SUCCEEDED
                            → FAILED
                   → CANCELLED
```

---

## Security

### API Key authentication

All endpoints except `/health` require `X-API-Key`. The middleware rejects requests with `401` if the key is missing or unknown.

Keys are loaded from the `API_KEYS` environment variable at startup:

```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

In development, two hardcoded keys are available when `API_KEYS` is not set:

| Key | Tenant | Scopes |
|---|---|---|
| `dev-key` | `tenant_dev` | `predict`, `read_models` |
| `admin-key` | `tenant_admin` | `predict`, `read_models`, `admin` |

**Do not use these in production.**

### Scopes

| Scope | Grants access to |
|---|---|
| `predict` | `/predict`, `/predict/batch`, `/predict/async*` |
| `read_models` | `/models` |
| `admin` | `/metrics`, `/debug/*` |

### Rate limiting

Per-tenant sliding-window limits are enforced by `RateLimitMiddleware`:

| Endpoint | Limit |
|---|---|
| `/predict` | 10 req/s |
| `/models` | 2 req/s |
| `/metrics` | 10 req/10s |

When `REDIS_URL` is set, limits are enforced across all processes using a Redis sorted set. Without Redis, limits are per-process only.

### Payload guard

Requests with a body larger than 1 MB are rejected with `413`.

---

## Observability

### Structured logging

All log output is JSON. Each log line includes `timestamp`, `level`, and `message`. Inference success logs additionally include `request_id`, `job_id`, `model`, `version`, `tenant_id`, and `latency_ms`.

Example:
```json
{"timestamp": "2026-04-27T15:00:00Z", "level": "INFO", "message": "inference_success", "model": "echo", "version": "v1", "latency_ms": 3.2}
```

### Prometheus metrics

Available at `GET /metrics` (requires `admin` scope).

| Metric | Type | Labels | Description |
|---|---|---|---|
| `inference_requests_total` | Counter | `model`, `version`, `tenant` | Total inference requests |
| `inference_errors_total` | Counter | `model`, `version`, `error_type`, `tenant` | Total errors by type |
| `inference_latency_seconds` | Histogram | `model`, `version`, `tenant` | End-to-end latency |
| `executor_inflight` | Gauge | `device` | Currently executing jobs |
| `executor_timeouts_total` | Counter | `device` | Executor timeouts |

### Request tracing

Every request gets an `X-Request-ID` header. If the client sends one, it is echoed back. If not, a UUID is generated. The ID is propagated through logs and job records.

---

## Execution Backends

The engine ships with three executor implementations. All implement `BaseExecutor`.

### InferenceExecutor (default)

`ThreadPoolExecutor`-backed. Works for any Python model. CPU and GPU pools are configured separately.

```python
# app/config/execution.py
EXECUTION_POLICY = {
    "my_model:v1": "gpu",   # routes to the GPU executor
    "my_model:v2": "cpu",
}
DEFAULT_EXECUTOR = "cpu"
```

CPU executor: 8 workers. GPU executor: 2 workers. Configurable in `deps.py`.

### OnnxExecutor

Uses ONNX Runtime's thread pool. ONNX Runtime releases the GIL during inference, so this gives real parallelism for CPU-bound models.

Requires: `pip install onnxruntime`

### TritonExecutor

Delegates inference to a remote [Triton Inference Server](https://github.com/triton-inference-server/server) via gRPC. Pre/postprocessing still runs locally; only the model call goes remote.

Requires: `pip install tritonclient[grpc]`

```python
from app.execution.triton_executor import TritonExecutor
executor = TritonExecutor(url="triton-host:8001", max_workers=8)
```

### Writing a custom executor

Subclass `BaseExecutor` and implement `submit()` and `submit_background()`:

```python
from app.execution.base import BaseExecutor

class MyExecutor(BaseExecutor):
    def submit(self, fn, *args, timeout_s=None):
        # run fn(*args), return result
        ...

    def submit_background(self, fn, *args):
        # fire-and-forget
        ...
```

Register it in `deps.py` and add it to the `ExecutionPolicy`.

---

## Routing Strategies

Routing resolves `(model, None)` → `(model, concrete_version)` when the client does not specify a version. Configured in `app/config/routing.py`.

### Static

Always routes to a fixed version.

```python
"my_model": {"strategy": "static", "version": "v2"}
```

### Canary

Routes a percentage of traffic to a new version, the rest to the primary.

```python
"my_model": {
    "strategy": "canary",
    "primary": "v1",
    "canary": "v2",
    "canary_percent": 10,   # 10% to v2
}
```

### A/B

Deterministically routes based on a hash of the request ID. Same request ID always goes to the same version.

```python
"my_model": {
    "strategy": "ab",
    "variants": {"v1": 70, "v2": 30},   # weights, must sum to 100
}
```

---

## Storage Backends

### Job store

| Backend | When used | Notes |
|---|---|---|
| `SQLiteJobStore` | `DATABASE_URL` not set | Default. Stored at `app/instance/jobs.db`. WAL mode enabled. |
| `PostgresJobStore` | `DATABASE_URL` is set | Uses `psycopg2` with a `ThreadedConnectionPool`. Schema is auto-created on first run. |

### Model artifact loader

| Loader | Use case |
|---|---|
| `LocalModelLoader` | Load artifacts from `model_artifacts/<name>/<version>/` on disk |
| `S3ModelLoader` | Download from `s3://<bucket>/<prefix>/<name>/<version>/`. Requires `boto3`. |

Loaders are not wired into the registry automatically — use them inside your `build_pipeline()` function:

```python
from app.domain.loading.local_loader import LocalModelLoader

def build_pipeline():
    loader = LocalModelLoader(root="model_artifacts")
    artifact_path = loader.load("my_model", "v1")
    model = MyModel(artifact_path)
    model.load()
    ...
```

---

## Model Setup CLI

The CLI deploys a trained artifact to the engine in one command — no boilerplate required.

### Installation

```bash
uv sync --extra cli   # or: pip install -e ".[cli]"
```

Set your Groq API key:

```bash
export GROQ_API_KEY=<your-key>
```

### Deploy a model

```bash
inference-engine deploy ./sentiment.pkl
```

Interactive flow: inspects the artifact, prompts for name/version/device/routing/sample input, generates `load()` and `predict()` via LLM, validates the pipeline, shows a preview, and writes files on confirmation.

Non-interactive (CI):

```bash
inference-engine deploy ./sentiment.pkl \
  --name sentiment \
  --version v1 \
  --device cpu \
  --routing static \
  --sample-input "this movie was great"
```

Dry run (validate but write nothing):

```bash
inference-engine deploy ./sentiment.pkl --dry-run \
  --name sentiment --version v1 --device cpu \
  --routing static --sample-input "great movie"
```

### Fix a broken pipeline

```bash
inference-engine fix models/sentiment/v1/
```

Reads the existing `definition.py`, validates it, and if it fails sends the error to the LLM for a fix. Shows a diff and writes only after confirmation.

### Supported frameworks

| Framework | Support |
|---|---|
| sklearn | Full — steps, feature count, class labels inferred automatically |
| xgboost | Partial — class name and basic hints |
| PyTorch | Not supported — use the [manual flow](#adding-a-model) |
| Generic | Fallback — class name only, LLM fills the gaps |

### Environment variables

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Required for code generation |
| `INFERENCE_ENGINE_LLM_MODEL` | Override default model (`llama-3.3-70b-versatile`) |

See `docs/cli/overview.md` for full reference.

---

## Running Tests

```bash
# Run all tests
pytest

# Run a specific phase
pytest tests/test_phase1.py
pytest tests/test_phase2.py
pytest tests/test_phase3.py
```

Tests use `httpx.TestClient` against the FastAPI app directly — no running server needed. The SQLite job store uses an in-memory database for test isolation.
