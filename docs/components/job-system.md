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

```python
# app/services/job_service.py
service = JobService(store)

job_id = service.create_job(model_name, model_version, payload)
job    = service.get_job(job_id)
service.mark_running(job_id)
service.mark_succeeded(job_id, result)
service.mark_failed(job_id, error_types, error_message)
count  = service.reap_stuck(before=datetime)
```

`create_job()` creates the record, immediately transitions it to `PENDING`, and increments the `job_queue_depth` metric.

`mark_running()` reads the job to get `model_name`/`model_version`, transitions to `RUNNING`, and decrements `job_queue_depth`.

`reap_stuck(before)` marks all `RUNNING` jobs whose `started_at` is before the given datetime as `FAILED`. Used by the stuck-job reaper.

---

## JobStore (abstract interface)

```python
# app/domain/jobs/job_store.py
class JobStore(ABC):
    def create(self, job: Job) -> None: ...
    def get(self, job_id: UUID) -> Job: ...          # raises KeyError if not found
    def update_status(self, job_id, status, ...) -> None: ...
    def update_result(self, job_id, result, finished_at) -> None: ...
    def update_error(self, job_id, error_types, error_message, finished_at) -> None: ...
    def reap_stuck(self, before: datetime) -> int: ...  # returns count reaped
```

---

## SQLiteJobStore

**File:** `app/infra/jobs/sqlite_job_store.py`

Default backend. Used when `DATABASE_URL` is not set.

- Stored at `app/instance/jobs.db` (created automatically).
- WAL mode enabled for concurrent read/write.
- Uses a per-operation connection to avoid snapshot isolation issues under concurrent threads.
- Pass `db_path=":memory:"` for test isolation — uses a single shared in-memory connection.
- Schema is auto-migrated on first run via a `schema_version` table.

---

## PostgresJobStore

**File:** `app/infra/jobs/postgres_job_store.py`

Used when `DATABASE_URL` is set.

- Backed by `psycopg2.pool.ThreadedConnectionPool` (min 1, max 10 connections).
- Schema (`jobs` table) is created automatically on first startup.
- Additive-only migrations tracked in `schema_migrations` table — columns are never dropped.
- `close()` releases all connections in the pool.

**Requires:** `psycopg2` (included in default dependencies).

```
DATABASE_URL=postgresql://user:password@localhost:5432/inference_engine
```

**Fallback behaviour:** If `DATABASE_URL` is set but Postgres is unreachable at startup, the engine logs an `ERROR` and falls back to SQLite. This is not safe in production — fix the DSN or the connection before deploying.

---

## Stuck-job reaper

When a worker process is killed while a job is `RUNNING`, that job stays stuck in `RUNNING` forever with no result. The reaper fixes this.

**arq cron task** (`app/infra/queue/worker.py`): runs every 10 minutes, marks any `RUNNING` job whose `started_at` is older than 10 minutes as `FAILED` with `error_message = "reaped: worker did not complete in time"`.

The reaper runs automatically when the arq worker is active. For the in-process fallback (no Redis), stuck jobs are less likely since the process lifecycle is tied to the API server.
