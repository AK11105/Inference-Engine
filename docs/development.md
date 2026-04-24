# Development Guide

---

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

---

## Setup

```bash
# Clone the repo
git clone <repo-url>
cd Inference-Engine

# Create virtual environment and install dependencies (uv)
uv sync

# Or with pip
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

**Dependencies** (from `pyproject.toml`):

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ≥0.128.0 | HTTP transport adapter |
| `uvicorn` | ≥0.40.0 | ASGI server |
| `pydantic` | ≥2.12.5 | Request/response schema validation |
| `prometheus-client` | ≥0.23.1 | Metrics instrumentation |

---

## Running the Server

```bash
uvicorn app.adapters.http.app:app --reload --port 8000
```

The `--reload` flag enables hot-reloading during development.

The server starts at `http://localhost:8000`.

---

## Project Structure

```
Inference-Engine/
├── app/
│   ├── __init__.py
│   ├── adapters/
│   │   └── http/
│   │       ├── app.py              # FastAPI app factory
│   │       ├── deps.py             # Dependency injection wiring
│   │       ├── middleware/
│   │       │   ├── auth.py
│   │       │   ├── rate_limit.py
│   │       │   └── payload_guard.py
│   │       ├── routes/
│   │       │   ├── __init__.py     # Router aggregation
│   │       │   ├── predict.py
│   │       │   ├── predict_batch.py
│   │       │   ├── predict_async.py
│   │       │   ├── predict_async_batch.py
│   │       │   ├── jobs.py
│   │       │   ├── models.py
│   │       │   ├── metrics.py
│   │       │   ├── debug.py
│   │       │   ├── health.py
│   │       │   └── ready.py
│   │       └── schemas/
│   │           ├── request.py
│   │           └── response.py
│   ├── config/
│   │   ├── routing.py              # Version routing rules
│   │   └── execution.py            # Executor assignment policy
│   ├── core/
│   │   ├── logging.py              # JSON structured logging
│   │   └── metrics.py              # Prometheus metrics
│   ├── domain/
│   │   ├── definitions/            # Pipeline factory modules
│   │   │   ├── echo_v1.py
│   │   │   └── echo_v2.py
│   │   ├── jobs/
│   │   │   ├── job.py              # Job dataclass
│   │   │   ├── job_state.py        # JobStatus enum
│   │   │   └── job_store.py        # Abstract JobStore
│   │   ├── models/
│   │   │   ├── base.py             # BaseModel ABC
│   │   │   └── echo_model.py       # EchoModel (reference)
│   │   ├── pipelines/
│   │   │   └── base.py             # InferencePipeline
│   │   ├── processing/
│   │   │   ├── pre.py              # BasePreprocessor + Identity
│   │   │   └── post.py             # BasePostprocessor + Identity
│   │   └── registry/
│   │       └── registry.py         # ModelRegistry
│   ├── execution/
│   │   ├── executor.py             # InferenceExecutor
│   │   └── execution_policy.py     # ExecutionPolicy
│   ├── infra/
│   │   └── jobs/
│   │       └── sqlite_job_store.py # SQLite implementation
│   ├── instance/
│   │   └── jobs.db                 # SQLite database (auto-created)
│   └── security/
│       ├── auth.py                 # API key → Identity
│       ├── permissions.py          # Scope enforcement
│       └── rate_limit.py           # Sliding window limiter
├── tests/
│   ├── curls.md                    # Manual curl test scripts
│   ├── run_abstract_classes.py
│   ├── run_prediction_service.py
│   └── run_registry_definitions.py
├── docs/                           # This documentation
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Development API Keys

Two keys are pre-configured for local development:

| Key | Scopes |
|---|---|
| `dev-key` | `predict`, `read_models` |
| `admin-key` | `predict`, `read_models`, `admin` |

To add a key, edit `app/security/auth.py`:

```python
API_KEYS["my-key"] = Identity(
    api_key="my-key",
    tenant_id="tenant_xyz",
    scopes={"predict"},
)
```

---

## Manual Testing

The `tests/curls.md` file contains a comprehensive set of `curl` commands covering:

- Health and readiness probes
- Sync, batch, async, and async-batch inference
- Authentication failures (missing key, invalid key)
- Scope enforcement
- Rate limiting (fire 15 requests rapidly)
- Payload size guard (send 2 MB body)
- Routing strategies (canary, A/B)
- Execution policy (CPU vs GPU executor selection)
- Metrics scraping

Run the server, then execute the curl commands from that file to validate the full system.

---

## Conventions

### Adding a New Route

1. Create a new file in `app/adapters/http/routes/`.
2. Define a `router = APIRouter()` and add route handlers.
3. Import and include the router in `app/adapters/http/routes/__init__.py`.

### Adding a New Service

1. Create the service class in `app/services/`.
2. Add a factory function in `app/adapters/http/deps.py`.
3. Inject via `Depends()` in route handlers.

### Adding Infrastructure

1. Implement the domain interface (e.g., `JobStore`) in `app/infra/`.
2. Wire the implementation in `deps.py`.
3. The domain layer must never import from `infra/`.

### Dependency Direction

```
adapters → services → domain ← infra
                    ↑
                 execution
                    ↑
                   core
```

- `domain/` has no outward dependencies (except `core/` for metrics).
- `services/` depends on `domain/` and `execution/`.
- `adapters/` depends on `services/` and `security/`.
- `infra/` depends on `domain/` (implements its interfaces).
- Nothing in `domain/` or `services/` imports from `adapters/` or `infra/`.

---

## Common Issues

**`ModuleNotFoundError: No module named 'app'`**

Run the server from the project root, not from inside `app/`:
```bash
cd Inference-Engine
uvicorn app.adapters.http.app:app --reload
```

**`KeyError: Job <uuid> not found`**

The SQLite database is created at `app/instance/jobs.db`. Ensure the `app/instance/` directory exists and is writable.

**`RuntimeError: Unknown executor 'tpu'`**

The `EXECUTION_POLICY` references an executor name that doesn't exist. Valid names are `"cpu"` and `"gpu"`. Check `app/config/execution.py`.

**`ValueError: No routing configuration for model 'X'`**

A request was made without an explicit `version` for a model that has no entry in `app/config/routing.py`. Either add a routing rule or always supply a version in requests.
