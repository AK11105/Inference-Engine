# Adding a Model

A model is a pipeline definition — a module that exposes `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()`.

---

## Directory layout

Two separate directories are involved:

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

`models/` contains Python code. `model_artifacts/` contains binary artifacts (weights, pickles, ONNX files, etc.). The registry scans `models/` at startup; `model_artifacts/` is a filesystem convention used by `LocalModelLoader` inside `build_pipeline()`.

---

---

## Step 1 — Implement the model

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

Rules: `load()` runs once at startup. `predict()` receives preprocessor output, not raw JSON. No HTTP or storage imports.

---

## Step 2 — Preprocessor / Postprocessor

```python
from app.domain.processing.pre import BasePreprocessor

class MyPreprocessor(BasePreprocessor):
    def transform(self, raw_input):
        return [float(v) for v in raw_input["features"]]
```

Use `IdentityPreprocessor` / `IdentityPostprocessor` if no transformation is needed.

---

## Step 3 — Validator (optional)

```python
from app.domain.validation.base import BaseValidator, ValidationError

class MyValidator(BaseValidator):
    def validate(self, model_input) -> None:
        if len(model_input) != 10:
            raise ValidationError(f"Expected 10 features, got {len(model_input)}")
```

`ValidationError` → HTTP 400. Omit the validator to use `NoOpValidator`.

---

## Step 4 — Pipeline definition

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

---

## Step 5 — Register

**Option A — Built-in:** add to `_definitions` in `app/domain/registry/registry.py`.

**Option B — Auto-discovery:** place `definition.py` at `models/<name>/<version>/definition.py`. The registry scans this directory at startup — no code change needed.

---

## Step 6 — Routing (optional)

Add to `app/config/routing.py` so clients can omit `version`:

```python
"my_model": {"strategy": "static", "version": "v1"}
```

---

## Step 7 — Test

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "my_model", "version": "v1", "data": {"features": [1,2,3]}}'
```

---

## Checklist

- [ ] `BaseModel` subclass with `load()` and `predict()`
- [ ] Preprocessor (or `IdentityPreprocessor`)
- [ ] Postprocessor (or `IdentityPostprocessor`)
- [ ] Validator (or omit for `NoOpValidator`)
- [ ] Pipeline definition with `MODEL_NAME`, `MODEL_VERSION`, `build_pipeline()`
- [ ] Registered (built-in or auto-discovery)
- [ ] Routing rule (if version should be optional)
- [ ] Execution policy entry (if not using default CPU executor)
