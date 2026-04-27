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
```

`create_job()` creates the record and immediately transitions it to `PENDING`.

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
- `close()` releases all connections in the pool.

**Requires:** `psycopg2` (included in default dependencies).

```
DATABASE_URL=postgresql://user:password@localhost:5432/inference_engine
```
