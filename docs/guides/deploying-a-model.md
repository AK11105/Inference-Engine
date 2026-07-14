# Deploying a Model

Two paths: use the CLI for automatic code generation, or write the pipeline definition manually.

---

## Option A — CLI (recommended)

```bash
uv sync --extra cli
export GROQ_API_KEY=<your-key>

inference-engine deploy ./my_model.pkl --allow-load
```

The CLI inspects the artifact, generates `load()` and `predict()`, validates the pipeline, and writes all files. The `--allow-load` flag permits pickle deserialization for full metadata extraction. See [CLI: deploy](../cli/deploy.md) for full reference.

!!! note "Pickle safety"
    Without `--allow-load`, pickle/joblib artifacts are inspected at the metadata level only (file size, format detection) — deserialization is skipped. In interactive mode, you'll be prompted to confirm.

---

## Option B — Manual

### 1. Implement the model

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

### 2. Add preprocessor / postprocessor

```python
from app.domain.processing.pre import BasePreprocessor

class MyPreprocessor(BasePreprocessor):
    def transform(self, raw_input):
        return [float(v) for v in raw_input["features"]]
```

Use `IdentityPreprocessor` / `IdentityPostprocessor` if no transformation is needed.

### 3. Write the pipeline definition

```python
# models/my_model/v1/definition.py
from app.domain.pipelines.base import InferencePipeline
from app.domain.processing.post import IdentityPostprocessor

MODEL_NAME = "my_model"
MODEL_VERSION = "v1"

def build_pipeline() -> InferencePipeline:
    from app.domain.models.my_model import MyModel
    from app.domain.processing.pre import MyPreprocessor
    model = MyModel()
    model.load()
    return InferencePipeline(
        preprocessor=MyPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
```

Place this file at `models/my_model/v1/definition.py`. The registry auto-discovers it at startup.

### 4. Add a routing rule (optional)

```python
# app/config/routing.py
ROUTES = {
    "my_model": {"strategy": "static", "version": "v1"},
}
```

### 5. Restart and test

```bash
uvicorn app.adapters.http.app:app --reload

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
- [ ] `definition.py` with `MODEL_NAME`, `MODEL_VERSION`, `build_pipeline()`
- [ ] Routing rule (if version should be optional)
