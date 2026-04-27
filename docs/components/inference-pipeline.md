# Inference Pipeline

**Files:** `app/domain/pipelines/base.py`, `app/domain/models/`, `app/domain/processing/`, `app/domain/validation/`

The pipeline is the unit of inference. It composes four components into a single `run()` call.

---

## Execution order

```
raw_input
    │
    ▼  preprocessor.transform()   raw JSON → model-ready format
    │
    ▼  validator.validate()        check shape / dtype / ranges  (optional)
    │
    ▼  model.predict()             pure inference
    │
    ▼  postprocessor.transform()   model output → response-ready format
    │
result
```

---

## BaseModel

```python
# app/domain/models/base.py
class BaseModel(ABC):
    def load(self) -> None: ...          # called once at startup
    def predict(self, x: Any) -> Any: ...
    def predict_batch(self, xs) -> list: ...  # default: loops predict()
```

- `load()` is called exactly once before any `predict()` call. Load weights, open file handles, initialize runtimes here.
- `predict()` receives the output of the preprocessor — not raw JSON.
- Override `predict_batch()` for vectorised or GPU-batched inference. The default loops `predict()`.

---

## BasePreprocessor / IdentityPreprocessor

```python
# app/domain/processing/pre.py
class BasePreprocessor(ABC):
    def transform(self, raw_input: Any) -> Any: ...

class IdentityPreprocessor(BasePreprocessor):
    def transform(self, raw_input: Any) -> Any:
        return raw_input
```

Use `IdentityPreprocessor` when the model accepts the raw JSON value directly.

---

## BasePostprocessor / IdentityPostprocessor

```python
# app/domain/processing/post.py
class BasePostprocessor(ABC):
    def transform(self, model_output: Any) -> Any: ...

class IdentityPostprocessor(BasePostprocessor):
    def transform(self, model_output: Any) -> Any:
        return model_output
```

Use `IdentityPostprocessor` when the model output is already JSON-serializable.

---

## BaseValidator / NoOpValidator

```python
# app/domain/validation/base.py
class ValidationError(ValueError): ...

class BaseValidator(ABC):
    def validate(self, model_input: Any) -> None: ...  # raise ValidationError on failure

class NoOpValidator(BaseValidator):
    def validate(self, model_input: Any) -> None:
        pass
```

Validators run on the **preprocessed** input — they see the model-ready format, not raw JSON. This is the right place to check array shape, dtype, value ranges, or required keys.

`ValidationError` propagates as `PredictionError` in the service layer → HTTP 400.

Omitting `validator` in `InferencePipeline(...)` defaults to `NoOpValidator`.

---

## InferencePipeline

```python
# app/domain/pipelines/base.py
class InferencePipeline:
    def __init__(
        self,
        preprocessor: BasePreprocessor,
        model: BaseModel,
        postprocessor: BasePostprocessor,
        validator: BaseValidator | None = None,
    ): ...

    def run(self, raw_input: Any) -> Any: ...
    def run_batch(self, raw_inputs) -> list: ...  # default: loops run()
```

One pipeline instance is created per `(model, version)` and reused for all requests. Override `run_batch()` for optimised batch execution.
