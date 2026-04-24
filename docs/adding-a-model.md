# Adding a Model

This guide walks through registering a new ML model in the inference engine. The process involves four steps: implement the model, implement pre/postprocessors, create a pipeline definition, and register it.

---

## Step 1: Implement the Model

Create a new file in `app/domain/models/` (or a subdirectory for organization).

```python
# app/domain/models/sentiment_model.py
from typing import Any
from app.domain.models.base import BaseModel

class SentimentModel(BaseModel):
    def __init__(self, model_path: str):
        self._model_path = model_path
        self._model = None

    def load(self) -> None:
        # Load your model artifact here
        # e.g., self._model = torch.load(self._model_path)
        import joblib
        self._model = joblib.load(self._model_path)

    def predict(self, x: Any) -> Any:
        # x is the output of your preprocessor
        return self._model.predict([x["text"]])[0]

    def predict_batch(self, xs) -> list:
        # Optional: override for vectorized batch inference
        texts = [item["text"] for item in xs]
        return self._model.predict(texts).tolist()
```

**Rules:**
- Do not import FastAPI, Pydantic, or HTTP concepts.
- `load()` must be safe to call multiple times (idempotent).
- `predict()` receives the output of your preprocessor, not the raw HTTP payload.

---

## Step 2: Implement Pre/Postprocessors

Create processors in `app/domain/processing/` or inline in your definition file.

```python
# app/domain/processing/sentiment_processors.py
from typing import Any
from app.domain.processing.pre import BasePreprocessor
from app.domain.processing.post import BasePostprocessor

class SentimentPreprocessor(BasePreprocessor):
    def transform(self, raw_input: Any) -> Any:
        # raw_input is the `data` field from the HTTP request
        return {
            "text": str(raw_input["text"]).strip().lower()
        }

class SentimentPostprocessor(BasePostprocessor):
    def transform(self, model_output: Any) -> Any:
        label_map = {0: "negative", 1: "neutral", 2: "positive"}
        return {
            "label": label_map.get(model_output, "unknown"),
            "raw": model_output,
        }
```

If no transformation is needed, use the built-ins:
- `IdentityPreprocessor` — passes input through unchanged
- `IdentityPostprocessor` — passes output through unchanged

---

## Step 3: Create a Pipeline Definition

Create a file in `app/domain/definitions/`. The filename convention is `{model_name}_v{N}.py`.

```python
# app/domain/definitions/sentiment_v1.py
from app.domain.models.sentiment_model import SentimentModel
from app.domain.processing.sentiment_processors import (
    SentimentPreprocessor,
    SentimentPostprocessor,
)
from app.domain.pipelines.base import InferencePipeline

MODEL_NAME = "sentiment"
MODEL_VERSION = "v1"

def build_pipeline() -> InferencePipeline:
    model = SentimentModel(model_path="models/sentiment_v1.pkl")
    model.load()

    return InferencePipeline(
        preprocessor=SentimentPreprocessor(),
        model=model,
        postprocessor=SentimentPostprocessor(),
    )
```

**Required exports:**

| Symbol | Type | Description |
|---|---|---|
| `MODEL_NAME` | `str` | Must be unique per model family |
| `MODEL_VERSION` | `str` | Must be unique per `(name, version)` pair |
| `build_pipeline` | `() -> InferencePipeline` | Factory called once on first request |

---

## Step 4: Register in the Registry

Open `app/domain/registry/registry.py` and add your definition:

```python
from app.domain.definitions import echo_v1, echo_v2, sentiment_v1  # add import

class ModelRegistry:
    def __init__(self):
        self._pipelines = {}
        self._definitions = {
            (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
            (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline,
            # Add your model here:
            (sentiment_v1.MODEL_NAME, sentiment_v1.MODEL_VERSION): sentiment_v1.build_pipeline,
        }
```

---

## Step 5: (Optional) Configure Routing

If you want version routing for your model, add an entry to `app/config/routing.py`:

```python
ROUTES = {
    "echo": { ... },
    "sentiment": {
        "strategy": "static",
        "version": "v1",
    },
}
```

Without a routing entry, clients must always supply an explicit `version` in their requests.

---

## Step 6: (Optional) Configure Execution Policy

To assign your model to a specific executor (e.g., GPU), add an entry to `app/config/execution.py`:

```python
EXECUTION_POLICY = {
    "echo:v1": "gpu",
    "echo:v2": "cpu",
    "sentiment:v1": "cpu",   # add this
}
```

If omitted, the `DEFAULT_EXECUTOR` (`"cpu"`) is used.

---

## Verification

After registering, restart the server and verify:

```bash
# Check the model appears in the registry
curl http://localhost:8000/models -H "X-API-Key: dev-key"

# Run a prediction
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "sentiment", "version": "v1", "data": {"text": "I love this"}}'

# Check it loaded into memory
curl http://localhost:8000/debug/models/loaded -H "X-API-Key: admin-key"
```

---

## Checklist

- [ ] Model class extends `BaseModel` and implements `load()` and `predict()`
- [ ] Preprocessor extends `BasePreprocessor` and implements `transform()`
- [ ] Postprocessor extends `BasePostprocessor` and implements `transform()`
- [ ] Definition file exports `MODEL_NAME`, `MODEL_VERSION`, `build_pipeline`
- [ ] `build_pipeline()` calls `model.load()` before returning the pipeline
- [ ] Definition is registered in `ModelRegistry._definitions`
- [ ] Routing config added (if version routing is desired)
- [ ] Execution policy set (if GPU or custom executor is needed)
