# Storage Configuration

## Job store

The job store backend is selected automatically based on `DATABASE_URL`.

**SQLite (default)**

Used when `DATABASE_URL` is not set. Stored at `app/instance/jobs.db`. Created automatically on first run.

```bash
# No configuration needed — just start the server
uvicorn app.adapters.http.app:app
```

**Postgres**

```bash
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/inference_engine
```

Schema is created automatically on first startup. Uses `asyncpg` connection pool (min 1, max 10).

!!! warning
    If `DATABASE_URL` is set but Postgres is unreachable at startup, the engine logs an error and falls back to SQLite. This is not safe in production.

---

## Artifact storage

Artifacts are loaded by `build_pipeline()` functions using a loader.

**Local (default)**

```python
from app.domain.loading.local_loader import LocalModelLoader

loader = LocalModelLoader(root="model_artifacts")
path = loader.load("my_model", "v1")
# → Path("model_artifacts/my_model/v1/")
```

**S3**

```python
from app.domain.loading.s3_loader import S3ModelLoader

loader = S3ModelLoader(bucket="my-bucket", prefix="models")
path = loader.load("my_model", "v1")
# downloads s3://my-bucket/models/my_model/v1/* → local temp dir
```

**Requires:** `pip install boto3`
