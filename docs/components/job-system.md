# Job System

**Files:** `app/domain/jobs/`, `app/services/job_service.py`, `app/infra/jobs/`

Every inference request — sync or async — creates a `Job` record. This gives a full audit trail regardless of execution mode.

---

## Job

```python
# app/domain/jobs/job.py
@dataclass
class Job:
    id: UUID
    model_name: str
    model_version: str
    payload: Any
    status: JobStatus
    device: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    result: Optional[Any]
    error_types: Optional[str]
    error_message: Optional[str]
```

---

## JobStatus

```python
class JobStatus(str, Enum):
    CREATED   = "created"
    PENDING   = "pending"
    RUNNING   = "running"
    SUCCEEDED = "succeeded"
    FAILED    = "failed"
    CANCELLED = "cancelled"
```

Lifecycle:

```
CREATED → PENDING → RUNNING → SUCCEEDED
                            → FAILED
                   → CANCELLED
```

`CREATED` and `PENDING` are set immediately in `JobService.create_job()`. `RUNNING` is set when the executor picks up the job. `SUCCEEDED` or `FAILED` is set when execution completes.

---

## JobService

All methods are `async`:

```python
# app/services/job_service.py
service = JobService(store)

job_id = await service.create_job(model_name, model_version, payload)
job    = await service.get_job(job_id)
await service.mark_running(job_id)
await service.mark_succeeded(job_id, result)
await service.mark_failed(job_id, error_types, error_message)
count  = await service.reap_stuck(before=datetime)
```

`create_job()` creates the record, immediately transitions it to `PENDING`, and increments the `job_queue_depth` metric.

`mark_running()` reads the job to get `model_name`/`model_version`, transitions to `RUNNING`, and decrements `job_queue_depth`.

`reap_stuck(before)` marks all `RUNNING` jobs whose `started_at` is before the given datetime as `FAILED`. Called at startup and by the arq cron task.

---

## JobStore (abstract interface)

All methods are `async`:

```python
# app/domain/jobs/job_store.py
class JobStore(ABC):
    async def create(self, job: Job) -> None: ...
    async def get(self, job_id: UUID) -> Job: ...          # raises KeyError if not found
    async def update_status(self, job_id, status, ...) -> None: ...
    async def update_result(self, job_id, result, finished_at) -> None: ...
    async def update_error(self, job_id, error_types, error_message, finished_at) -> None: ...
    async def reap_stuck(self, before: datetime) -> int: ...  # returns count reaped
```

---

## SQLiteJobStore

**File:** `app/infra/jobs/sqlite_job_store.py`

Default backend. Used when `DATABASE_URL` is not set.

- Stored at `app/instance/jobs.db` (created automatically).
- WAL mode enabled for concurrent read/write.
- Sync SQLite operations are offloaded to a thread-pool executor via `loop.run_in_executor` so they never block the event loop.
- Pass `db_path=":memory:"` for test isolation — uses a single shared in-memory connection.
- Schema is auto-migrated on first run via a `schema_version` table.

---

## PostgresJobStore

**File:** `app/infra/jobs/postgres_job_store.py`

Used when `DATABASE_URL` is set. Backed by `asyncpg` — fully non-blocking, event-loop safe.

Initialise via the async factory (called automatically by the lifespan):

```python
store = await PostgresJobStore.create_pool(dsn=DATABASE_URL)
```

- Uses an `asyncpg` connection pool (min 1, max 10 connections).
- Schema (`jobs` table) is created automatically on first startup.
- Additive-only migrations tracked in `schema_migrations` table — columns are never dropped.
- `await store.close()` releases all connections in the pool.

**Requires:** `asyncpg` (included in default dependencies).

```
DATABASE_URL=postgresql://user:password@localhost:5432/inference_engine
```

**Fallback behaviour:** If `DATABASE_URL` is set but Postgres is unreachable at startup, the engine logs an `ERROR` and falls back to SQLite. This is not safe in production.

---

## Stuck-job reaper

When a worker process is killed while a job is `RUNNING`, that job stays stuck forever. The reaper fixes this.

**On startup** (`app/adapters/http/app.py` lifespan): marks any `RUNNING` job older than 10 minutes as `FAILED` before the server begins accepting requests. Handles crash recovery.

**arq cron task** (`app/infra/queue/worker.py`): runs every 10 minutes, marks any `RUNNING` job whose `started_at` is older than 10 minutes as `FAILED` with `error_message = "reaped: worker did not complete in time"`.
