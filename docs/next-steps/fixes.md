# Fixes

All changes needed to bring the current system to production-ready state.
Ordered by priority: correctness first, then robustness, then polish.

---

## P0 — Correctness (breaks things in production)

### 1. Exempt `/ready` from auth

**File:** `app/adapters/http/middleware/auth.py`

`/ready` is a readiness probe. Load balancers and orchestrators (k8s, ECS) call it
without credentials. Currently it returns `401`.

```python
# Before
if request.url.path in {"/health"}:

# After
if request.url.path in {"/health", "/ready"}:
```

---

### 2. Fix Redis rate limiter TOCTOU race

**File:** `app/security/rate_limit.py`

The current pipeline (remove stale → zcard → zadd → expire) is not atomic.
Two concurrent requests can both read `count_before_add < rate` and both be allowed through.

Replace the pipeline with a Lua script that executes atomically:

```python
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local rate = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('zremrangebyscore', key, '-inf', now - window)
local count = redis.call('zcard', key)
if count >= rate then return 0 end
redis.call('zadd', key, now, member)
redis.call('expire', key, window + 1)
return 1
"""

def allow(self, key: str) -> bool:
    import uuid as _uuid
    now = time.time()
    zkey = f"ratelimit:{self._name}:{key}"
    member = f"{now}:{_uuid.uuid4().hex}"
    result = self._redis.eval(_LUA, 1, zkey, now, self._per_seconds, self._rate, member)
    return bool(result)
```

---

### 3. Add max_items limit to batch endpoints

**File:** `app/adapters/http/schemas/request.py`

An unbounded batch blocks an executor thread for its full duration, starving other requests.

```python
# Before
class PredictBatchRequest(BaseModel):
    items: conlist(Any, min_length=1)

# After
class PredictBatchRequest(BaseModel):
    items: conlist(Any, min_length=1, max_length=256)
```

Apply the same constraint to `PredictAsyncBatchRequest` (currently typed as plain `list`
with no constraints at all).

---

## P1 — Robustness (silent failures, hard-to-debug issues)

### 4. Log warnings on discovery failures

**File:** `app/domain/registry/registry.py`

Silent `pass` on a malformed `definition.py` means a user gets no feedback when their
model fails to load. Replace with a warning log.

```python
# Before
except Exception:
    pass

# After
except Exception as exc:
    import logging
    logging.getLogger(__name__).warning(
        "Failed to load definition %s: %s", definition_file, exc
    )
```

---

### 5. Cache `get_prediction_service()`

**File:** `app/adapters/http/deps.py`

Every request creates a new `PredictionService` instance. The service is stateless so
it's harmless, but it's inconsistent with every other provider in the file.

```python
# Before
def get_prediction_service() -> PredictionService:

# After
@lru_cache
def get_prediction_service() -> PredictionService:
```

Also add `_deps.get_prediction_service.cache_clear()` to the shutdown block in `app.py`.

---

### 6. Startup validation report

**File:** `app/domain/registry/registry.py`

`warm_up()` currently either succeeds silently or raises. Add per-model logging so
operators can see exactly which models loaded and which failed, with timing.

```python
def warm_up(self) -> None:
    import logging, time
    logger = logging.getLogger(__name__)
    for key in self._definitions:
        t = time.time()
        try:
            self.get(key[0], key[1])
            logger.info("registry: loaded %s:%s in %.0fms", key[0], key[1], (time.time()-t)*1000)
        except Exception as exc:
            logger.error("registry: failed to load %s:%s — %s", key[0], key[1], exc)
```

---

## P2 — Configuration and dependencies

### 7. Remove unused `asyncpg` dependency

**File:** `pyproject.toml`

`asyncpg` is declared but `PostgresJobStore` uses `psycopg2`. Remove it.

```toml
# Remove this line:
"asyncpg>=0.30.0",
```

---

### 8. Move `pytest` to dev dependencies

**File:** `pyproject.toml`

`pytest` ships in production installs. Move it to an optional group.

```toml
[project.optional-dependencies]
dev = [
    "pytest>=9.0.3",
    "httpx>=0.28.1",
]
```

(`httpx` is also test-only.)

---

### 9. Pin dependency versions

**File:** `pyproject.toml`

Open `>=` ranges mean a future `uv sync` can silently pull in a breaking version.
Pin to the versions currently in `uv.lock`:

```toml
"fastapi==0.128.0",
"prometheus-client==0.23.1",
"pydantic==2.12.5",
"uvicorn==0.40.0",
"redis==5.3.1",
"arq==0.28.0",
"python-dotenv==1.2.2",
"psycopg2-binary==2.9.12",
```

---

### 10. Make executor worker counts configurable

**File:** `app/adapters/http/deps.py`

CPU=8, GPU=2 are hardcoded. Read from env vars so they can be tuned per deployment
without code changes.

```python
@lru_cache
def get_cpu_executor() -> InferenceExecutor:
    workers = int(os.environ.get("CPU_EXECUTOR_WORKERS", "8"))
    return InferenceExecutor(device="cpu", max_workers=workers)

@lru_cache
def get_gpu_executor() -> InferenceExecutor:
    workers = int(os.environ.get("GPU_EXECUTOR_WORKERS", "2"))
    return InferenceExecutor(device="gpu", max_workers=workers)
```

---

## P3 — Missing infrastructure

### 11. Add a Dockerfile

The engine has no container definition. Minimum viable:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev
COPY app/ app/
CMD ["uvicorn", "app.adapters.http.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 12. Add DB migration strategy

`PostgresJobStore` drops and recreates the table when the schema version is behind.
That destroys job history. Replace with additive-only migrations (add columns, never drop).
A simple versioned SQL file approach is sufficient — no need for Alembic.

---

## Summary

| # | File | Change | Priority |
|---|---|---|---|
| 1 | `middleware/auth.py` | Exempt `/ready` from auth | P0 |
| 2 | `security/rate_limit.py` | Atomic Lua script for Redis limiter | P0 |
| 3 | `schemas/request.py` | Add `max_length` to batch items | P0 |
| 4 | `registry/registry.py` | Log warnings on discovery failures | P1 |
| 5 | `deps.py` | Cache `get_prediction_service` | P1 |
| 6 | `registry/registry.py` | Startup validation report in `warm_up()` | P1 |
| 7 | `pyproject.toml` | Remove unused `asyncpg` | P2 |
| 8 | `pyproject.toml` | Move `pytest`/`httpx` to dev deps | P2 |
| 9 | `pyproject.toml` | Pin all dependency versions | P2 |
| 10 | `deps.py` | Env-var-configurable executor worker counts | P2 |
| 11 | `Dockerfile` | Add container definition | P3 |
| 12 | `infra/jobs/` | Safe additive DB migrations | P3 |
