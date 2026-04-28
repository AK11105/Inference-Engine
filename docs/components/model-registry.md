# ModelRegistry

**File:** `app/domain/registry/registry.py`

Thread-safe, lazy-loading cache of `InferencePipeline` instances keyed by `(model_name, version)`.

---

## Behaviour

- Pipelines are built on first access and cached in an LRU `OrderedDict`.
- Each `(name, version)` key has its own `threading.Lock` — two concurrent requests for the same unloaded model will not both call `build_pipeline()`. One builds; the other waits and receives the cached result.
- `warm_up()` is called at startup (via the FastAPI lifespan hook) to eagerly load all pipelines so the first request pays no loading cost.
- When `max_loaded` is set, the least-recently-used pipeline is evicted once the cache exceeds the limit. Evicted pipelines are rebuilt on next access.

---

## API

```python
registry = ModelRegistry(models_dir="models", max_loaded=10)

pipeline = registry.get("echo", "v1")       # loads on first call, cached thereafter
registry.warm_up()                           # eagerly load all registered pipelines
registry.is_ready() -> bool                 # True when all pipelines are loaded
registry.list_models() -> list[tuple]       # [(name, version), ...]
registry.reload("echo", "v1")              # hot-reload: evict + rebuild without restart
```

`get()` raises `ModelNotFoundError` if no definition exists for the requested `(name, version)`.

---

## LRU eviction

```python
# Keep at most 5 pipelines in memory at once
registry = ModelRegistry(max_loaded=5)
```

When the 6th pipeline is loaded, the least-recently-used one is evicted. It will be rebuilt on next access. Default is `None` (unlimited — all pipelines stay in memory).

---

## Hot-reload

```python
registry.reload("my_model", "v2")
```

Evicts the cached pipeline and calls `build_pipeline()` fresh. Thread-safe: in-flight requests using the old pipeline complete normally. Also available via the admin API — see [Admin API](../api/admin.md).

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
