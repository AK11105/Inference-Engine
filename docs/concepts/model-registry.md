# Model Registry

**File:** `app/domain/registry/registry.py`

Thread-safe, lazy-loading cache of `InferencePipeline` instances keyed by `(model_name, version)`.

---

## Behaviour

- Pipelines are built on first access and cached in an LRU `OrderedDict`.
- Each `(name, version)` key has its own `threading.Lock` — concurrent requests for the same unloaded model will not both call `build_pipeline()`.
- `warm_up()` is called at startup to eagerly load all pipelines so the first request pays no loading cost.
- When `max_loaded` is set, the least-recently-used pipeline is evicted once the cache exceeds the limit.

---

## API

```python
registry = ModelRegistry(models_dir="models", max_loaded=10)

pipeline = registry.get("echo", "v1")       # loads on first call, cached thereafter
registry.warm_up()                           # eagerly load all registered pipelines
registry.is_ready() -> bool
registry.list_models() -> list[tuple]        # [(name, version), ...]
registry.reload("echo", "v1")               # hot-reload: evict + rebuild without restart
```

`get()` raises `ModelNotFoundError` if no definition exists for the requested `(name, version)`.

---

## Definition sources

**Built-in:** Defined directly in `_definitions` inside `ModelRegistry.__init__()`.

**Auto-discovered:** The registry scans `models/<name>/<version>/definition.py` at startup. Any file that exposes `MODEL_NAME`, `MODEL_VERSION`, and `build_pipeline()` is registered automatically — no code change needed.

```
models/
└── my_model/
    └── v1/
        └── definition.py
```

---

## Hot-reload

```python
registry.reload("my_model", "v2")
```

Evicts the cached pipeline and calls `build_pipeline()` fresh. In-flight requests using the old pipeline complete normally. Also available via `POST /admin/models/{name}/{version}/reload`.

---

## LRU eviction

```python
registry = ModelRegistry(max_loaded=5)
```

When the 6th pipeline is loaded, the least-recently-used one is evicted. Default is `None` (unlimited).
