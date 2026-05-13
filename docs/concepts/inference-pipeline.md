# Inference Pipeline

**Files:** `app/domain/pipelines/base.py`, `app/domain/models/`, `app/domain/processing/`, `app/domain/validation/`

The pipeline is the unit of inference. It composes four components into a single `run()` call.

---

## Execution order

![Inference pipeline data flow diagram](../assets/inference-pipeline-light.png#only-light)
![Inference pipeline data flow diagram](../assets/inference-pipeline-dark.png#only-dark)

---

## BaseModel

```python
class BaseModel(ABC):
    def load(self) -> None: ...          # called once at startup
    def predict(self, x: Any) -> Any: ...
    def predict_batch(self, xs) -> list: ...  # default: loops predict()
```

- `load()` is called exactly once before any `predict()` call.
- `predict()` receives the output of the preprocessor — not raw JSON.
- Override `predict_batch()` for vectorised or GPU-batched inference.

---

## Preprocessor / Postprocessor

```python
class BasePreprocessor(ABC):
    def transform(self, raw_input: Any) -> Any: ...

class BasePostprocessor(ABC):
    def transform(self, model_output: Any) -> Any: ...
```

Use `IdentityPreprocessor` / `IdentityPostprocessor` when no transformation is needed.

---

## Validator

```python
class BaseValidator(ABC):
    def validate(self, model_input: Any) -> None: ...  # raise ValidationError on failure
```

Validators run on the **preprocessed** input. `ValidationError` propagates as HTTP 400. Omitting `validator` defaults to `NoOpValidator`.

---

## InferencePipeline

```python
class InferencePipeline:
    def __init__(
        self,
        preprocessor: BasePreprocessor,
        model: BaseModel,
        postprocessor: BasePostprocessor,
        validator: BaseValidator | None = None,
    ): ...

    def run(self, raw_input: Any) -> Any: ...
    def run_batch(self, raw_inputs) -> list: ...
```

One pipeline instance is created per `(model, version)` and reused for all requests.
