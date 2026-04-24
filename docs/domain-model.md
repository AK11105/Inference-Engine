# Domain Model

The domain layer (`app/domain/`) contains the core abstractions of the inference engine. It has no dependency on FastAPI, HTTP, or any infrastructure concern.

---

## BaseModel

**Location:** `app/domain/models/base.py`

The abstract base class for all inference models.

```python
class BaseModel(ABC):
    def load(self) -> None: ...
    def predict(self, x: Any) -> Any: ...
    def predict_batch(self, xs: Iterable[Any]) -> list[Any]: ...
```

| Method | Contract |
|---|---|
| `load()` | Load model artifacts into memory. Called once before inference. Must be idempotent. |
| `predict(x)` | Run inference on a single input. Input/output types are model-defined. |
| `predict_batch(xs)` | Batch inference. Default implementation is sequential `predict()` calls. Override for optimized batching. |

**Rules:**
- Models must not import HTTP, Pydantic, or transport concepts.
- Models must not know about job IDs, request IDs, or tenants.
- `load()` is called by the pipeline factory (`build_pipeline()`), not by the model itself.

---

## BasePreprocessor / BasePostprocessor

**Location:** `app/domain/processing/pre.py`, `app/domain/processing/post.py`

```python
class BasePreprocessor(ABC):
    def transform(self, raw_input: Any) -> Any: ...

class BasePostprocessor(ABC):
    def transform(self, model_output: Any) -> Any: ...
```

**Built-in implementations:**

| Class | Behavior |
|---|---|
| `IdentityPreprocessor` | Returns input unchanged. Use for models that accept raw payloads. |
| `IdentityPostprocessor` | Returns output unchanged. Use when model output is already response-ready. |

**Rules:**
- Preprocessors transform external input into model-ready input.
- Postprocessors transform model output into response-ready output.
- No hidden transformations inside models — all transformations must be in explicit pre/postprocessors.

---

## InferencePipeline

**Location:** `app/domain/pipelines/base.py`

Composes a preprocessor, model, and postprocessor into a single executable unit.

```python
class InferencePipeline:
    def __init__(
        self,
        preprocessor: BasePreprocessor,
        model: BaseModel,
        postprocessor: BasePostprocessor,
    ): ...

    def run(self, raw_input: Any) -> Any: ...
    def run_batch(self, raw_inputs) -> list: ...
```

**Execution flow:**
```
raw_input
    → preprocessor.transform(raw_input)   → model_input
    → model.predict(model_input)           → model_output
    → postprocessor.transform(model_output) → final_result
```

`run_batch()` defaults to sequential `run()` calls. Override at the pipeline level for true batch optimization.

---

## ModelRegistry

**Location:** `app/domain/registry/registry.py`

Resolves `(model_name, version)` to a loaded `InferencePipeline`. Implements lazy loading and in-memory caching.

```python
class ModelRegistry:
    def get(self, model_name: str, version: str) -> InferencePipeline: ...
    def list_models(self) -> List[Tuple[str, str]]: ...
```

**Behavior:**
- On first `get(name, version)`: calls the registered factory function, caches the result.
- On subsequent calls: returns the cached pipeline (no re-loading).
- Raises `ModelNotFoundError` if `(name, version)` is not in `_definitions`.

**Adding models to the registry:**
Pipelines are registered in `__init__` via a `_definitions` dict mapping `(name, version)` → `build_pipeline` callable. See [Adding a Model](./adding-a-model.md).

---

## Pipeline Definitions

**Location:** `app/domain/definitions/`

Each file in this directory is a pipeline factory module. It must export:

| Symbol | Type | Description |
|---|---|---|
| `MODEL_NAME` | `str` | Registered model name |
| `MODEL_VERSION` | `str` | Version string (e.g., `"v1"`) |
| `build_pipeline()` | `() -> InferencePipeline` | Factory that constructs and returns a loaded pipeline |

**Example (`echo_v1.py`):**
```python
MODEL_NAME = "echo"
MODEL_VERSION = "v1"

def build_pipeline() -> InferencePipeline:
    model = EchoModel()
    model.load()
    return InferencePipeline(
        preprocessor=IdentityPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
```

---

## Job

**Location:** `app/domain/jobs/job.py`

Represents a single inference request tracked through its lifecycle.

```python
@dataclass
class Job:
    id: UUID
    model_name: str
    model_version: str
    payload: Any
    status: JobStatus
    device: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    result: Optional[Any]
    error_types: Optional[str]
    error_message: Optional[str]
```

---

## JobStatus

**Location:** `app/domain/jobs/job_state.py`

```python
class JobStatus(str, Enum):
    CREATED   = "created"
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
    CANCELLED = "cancelled"
```

**State transitions:**
```
CREATED → PENDING → RUNNING → SUCCEEDED
                            → FAILED
```

---

## JobStore

**Location:** `app/domain/jobs/job_store.py`

Abstract interface for job persistence. The domain layer depends on this interface; the infrastructure layer provides the implementation.

```python
class JobStore(ABC):
    def create(self, job: Job) -> None: ...
    def get(self, job_id: UUID) -> Job: ...
    def update_status(self, job_id, status, started_at=None, finished_at=None) -> None: ...
    def update_result(self, job_id, result, finished_at) -> None: ...
    def update_error(self, job_id, error_types, error_message, finished_at) -> None: ...
```

**Current implementation:** `SQLiteJobStore` (`app/infra/jobs/sqlite_job_store.py`)

The SQLite store uses a single connection with `check_same_thread=False`. The database file is created at `app/instance/jobs.db` on first run.

---

## EchoModel (Reference Implementation)

**Location:** `app/domain/models/echo_model.py`

A no-op model that echoes its input. Used to validate the inference pipeline end-to-end without a real ML model.

```python
class EchoModel(BaseModel):
    def load(self) -> None:
        pass  # no artifacts

    def predict(self, x: Any) -> Any:
        return {"echo": x}
```

This model is registered as both `echo:v1` and `echo:v2` (identical behavior, different version labels) to demonstrate routing and versioning.
