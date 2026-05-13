# Model Definition Schema

A model definition is a Python module at `models/<name>/<version>/definition.py` that exposes three things:

```python
MODEL_NAME: str       # must match the name used in requests
MODEL_VERSION: str    # must match the version used in requests

def build_pipeline() -> InferencePipeline:
    ...               # called once at startup; returns a ready-to-use pipeline
```

---

## Minimal example

```python
from app.domain.models.base import BaseModel
from app.domain.processing.pre import IdentityPreprocessor
from app.domain.processing.post import IdentityPostprocessor
from app.domain.pipelines.base import InferencePipeline

MODEL_NAME = "my_model"
MODEL_VERSION = "v1"

class MyModel(BaseModel):
    def load(self) -> None:
        import joblib
        self._clf = joblib.load("model_artifacts/my_model/v1/model.pkl")

    def predict(self, x):
        return self._clf.predict([x])[0]

def build_pipeline() -> InferencePipeline:
    model = MyModel()
    model.load()
    return InferencePipeline(
        preprocessor=IdentityPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
```

---

## Rules

- `build_pipeline()` is called once at startup. Do not defer loading to `predict()`.
- `predict()` receives the output of `preprocessor.transform()`, not raw JSON.
- No HTTP, FastAPI, or storage SDK imports inside a definition file.
- `MODEL_NAME` and `MODEL_VERSION` must exactly match what clients send in requests.

---

## Auto-discovery

Place `definition.py` at `models/<name>/<version>/definition.py`. The registry scans this directory at startup — no code change needed. Malformed files are skipped silently.
