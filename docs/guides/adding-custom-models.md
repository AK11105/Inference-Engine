# Adding Custom Models

A model is a pipeline definition — a module that exposes `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()`.

---

## Directory layout

```
models/
└── my_model/
    └── v1/
        └── definition.py       ← registry entry point (auto-discovered)

model_artifacts/
└── my_model/
    └── v1/
        └── model.pkl           ← artifact file
```

`models/` contains Python code. `model_artifacts/` contains binary artifacts. The registry scans `models/` at startup.

---

## Step 1 — Implement the model class

```python
# app/domain/models/my_model.py
from app.domain.models.base import BaseModel

class MyModel(BaseModel):
    def load(self) -> None:
        import joblib
        self._clf = joblib.load("model_artifacts/my_model/v1/model.pkl")

    def predict(self, x):
        return self._clf.predict([x])[0]
```

Rules: `load()` runs once at startup. `predict()` receives preprocessor output, not raw JSON.

---

## Step 2 — Preprocessor / Postprocessor

```python
from app.domain.processing.pre import BasePreprocessor

class MyPreprocessor(BasePreprocessor):
    def transform(self, raw_input):
        return [float(v) for v in raw_input["features"]]
```

---

## Step 3 — Validator (optional)

```python
from app.domain.validation.base import BaseValidator, ValidationError

class MyValidator(BaseValidator):
    def validate(self, model_input) -> None:
        if len(model_input) != 10:
            raise ValidationError(f"Expected 10 features, got {len(model_input)}")
```

`ValidationError` → HTTP 400.

---

## Step 4 — Pipeline definition

```python
# models/my_model/v1/definition.py
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

---

## Step 5 — Register

**Auto-discovery (recommended):** place `definition.py` at `models/<name>/<version>/definition.py`. No code change needed.

**Built-in:** add to `_definitions` in `app/domain/registry/registry.py`.

---

## Step 6 — Routing (optional)

```python
# app/config/routing.py
ROUTES = {
    "my_model": {"strategy": "static", "version": "v1"},
}
```

---

## Step 7 — Test

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "my_model", "version": "v1", "data": {"features": [1,2,3]}}'
```
