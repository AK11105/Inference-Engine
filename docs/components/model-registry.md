# ModelRegistry

**File:** `app/domain/registry/registry.py`

Thread-safe, lazy-loading cache of `InferencePipeline` instances keyed by `(model_name, version)`.

---

## Behaviour

- Pipelines are built on first access and cached for the lifetime of the process.
- Each `(name, version)` key has its own `threading.Lock` — two concurrent requests for the same model will not both call `build_pipeline()`. One builds; the other waits and receives the cached result.
- `warm_up()` is called at startup (via the FastAPI lifespan hook) to eagerly load all pipelines so the first request pays no loading cost.

---

## API

```python
registry = ModelRegistry(models_dir="models")  # default: "models/"

pipeline = registry.get("echo", "v1")   # loads on first call, cached thereafter
registry.warm_up()                       # eagerly load all registered pipelines
registry.is_ready() -> bool             # True when all pipelines are loaded
registry.list_models() -> list[tuple]   # [(name, version), ...]
```

`get()` raises `ModelNotFoundError` if no definition exists for the requested `(name, version)`.

---

## Definition sources

Definitions are loaded from two places, merged at construction time. Discovered definitions override built-ins on key collision.

**1. Built-in (hardcoded)**

Defined directly in `_definitions` inside `ModelRegistry.__init__()`:

```python
from app.domain.definitions import echo_v1, echo_v2

self._definitions = {
    (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
    (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline,
}
```

**2. Auto-discovered**

The registry scans `models/<name>/<version>/definition.py` at startup. Any file that exposes `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()` is registered automatically — no code change needed.

```
models/
└── my_model/
    └── v1/
        └── definition.py
```

Malformed definition files are skipped silently.

---

## Adding a model

See [Adding a Model](../guides/adding-a-model.md).
