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

---

## Adding a custom format extractor

If your model uses a format not covered by the built-in extractors (GGUF, MLX, CoreML, etc.), you can add support without modifying inspector internals.

### 1. Create the extractor

```python
# app/cli/core/extractors/gguf_extractor.py
from app.cli.core.extractors.base import BaseExtractor


class GGUFExtractor(BaseExtractor):
    name = "gguf"
    priority = 70  # higher than built-ins (60), tried first

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("extension") == ".gguf"

    def extract(self, path: str, raw_facts: dict) -> dict:
        # Parse your format, populate raw_facts
        raw_facts["framework"] = "llama_cpp"
        raw_facts["format"] = "gguf"
        return raw_facts
```

### 2. Register it

Add the import and registration to `app/cli/core/extractors/__init__.py`:

```python
from .gguf_extractor import GGUFExtractor

def default_registry() -> ExtractorRegistry:
    reg = ExtractorRegistry()
    # ... existing registrations ...
    reg.register(GGUFExtractor())
    return reg
```

Or register dynamically at runtime without modifying any built-in files:

```python
from app.cli.core.extractors import default_registry
from my_plugin.extractors import GGUFExtractor

registry = default_registry()
registry.register(GGUFExtractor())
```

### 3. Add format detection (optional)

If the format isn't detected by extension or magic bytes, add an entry to the `_detect_format` function in `_INSPECT_SCRIPT` inside `inspector.py`, or rely on extension-based detection in `_EXT_MAP`.

See [CLI: deploy — Extractor registry](../cli/deploy.md#extractor-registry-plugin-based) for full reference.
