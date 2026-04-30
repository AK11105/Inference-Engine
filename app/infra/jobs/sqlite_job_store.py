import json
import sqlite3
import threading
from datetime import datetime, timezone
from uuid import UUID
from typing import Any, Optional

from app.domain.jobs import Job, JobStatus, JobStore

_CURRENT_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    device TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    error_type TEXT,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


class SQLiteJobStore(JobStore):
    """
    SQLite-backed job store.

    Uses a new connection per operation to avoid WAL snapshot isolation
    issues when multiple threads read/write concurrently.
    """

    def __init__(self, db_path: str = "app/instance/jobs.db"):
        self._db_path = db_path
        self._lock = threading.Lock()
        # In-memory databases are per-connection; reuse a single connection.
        self._shared_conn: sqlite3.Connection | None = (
            self._make_conn() if db_path == ":memory:" else None
        )
        self._migrate()

    def _make_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _connect(self) -> sqlite3.Connection:
        return self._shared_conn if self._shared_conn is not None else self._make_conn()

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.executescript(_DDL)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            stored = row["version"] if row else 0
            if stored < _CURRENT_SCHEMA_VERSION:
                conn.executescript(
                    """
                    DROP TABLE IF EXISTS jobs;
                    CREATE TABLE jobs (
                        id TEXT PRIMARY KEY,
                        model_name TEXT NOT NULL,
                        model_version TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL,
                        device TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        result TEXT,
                        error_type TEXT,
                        error_message TEXT
                    );
                    DELETE FROM schema_version;
                    """
                )
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (_CURRENT_SCHEMA_VERSION,),
                )
                conn.commit()

    def create(self, job: Job) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(job.id), job.model_name, job.model_version,
                    json.dumps(job.payload), job.status.value, job.device,
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.finished_at.isoformat() if job.finished_at else None,
                    json.dumps(job.result) if job.result is not None else None,
                    job.error_types if job.error_types is not None else None,
                    job.error_message if job.error_message is not None else None,
                ),
            )
            conn.commit()

    def get(self, job_id: UUID) -> Job:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ?", (str(job_id),)
            ).fetchone()

        if not row:
            raise KeyError(f"Job {job_id} not found")

        return Job(
            id=UUID(row["id"]),
            model_name=row["model_name"],
            model_version=row["model_version"],
            payload=json.loads(row["payload"]),
            status=JobStatus(row["status"]),
            device=row["device"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            result=json.loads(row["result"]) if row["result"] else None,
            error_types=row["error_type"],
            error_message=row["error_message"],
        )

    def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at) WHERE id = ?",
                (
                    status.value,
                    started_at.isoformat() if started_at else None,
                    finished_at.isoformat() if finished_at else None,
                    str(job_id),
                ),
            )
            conn.commit()

    def update_result(self, job_id: UUID, result: Any, finished_at: datetime) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET result = ?, finished_at = ?, status = ? WHERE id = ?",
                (json.dumps(result), finished_at.isoformat(), JobStatus.SUCCEEDED.value, str(job_id)),
            )
            conn.commit()

    def update_error(
        self, job_id: UUID, error_types: str, error_message: str, finished_at: datetime
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET error_type = ?, error_message = ?, finished_at = ?, status = ? WHERE id = ?",
                (error_types, error_message, finished_at.isoformat(), JobStatus.FAILED.value, str(job_id)),
            )
            conn.commit()

    def reap_stuck(self, before: datetime) -> int:
        """Mark RUNNING jobs whose started_at is before `before` as FAILED."""
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE jobs
                SET status = ?, error_message = 'reaped: worker did not complete in time',
                    finished_at = ?
                WHERE status = ? AND started_at < ?
                """,
                (
                    JobStatus.FAILED.value,
                    datetime.now(timezone.utc).isoformat(),
                    JobStatus.RUNNING.value,
                    before.isoformat(),
                ),
            )
            conn.commit()
            return cur.rowcount
