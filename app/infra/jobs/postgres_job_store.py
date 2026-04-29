"""
PostgreSQL-backed JobStore using psycopg2 with additive-only migrations.

Schema changes are applied as additive ALTER TABLE statements — columns are
never dropped, so existing job history is preserved across upgrades.
"""
import json
import os
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.domain.jobs import Job, JobStatus, JobStore

# Initial table creation (version 1)
_DDL_V1 = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    model_name    TEXT NOT NULL,
    model_version TEXT NOT NULL,
    payload       TEXT NOT NULL,
    status        TEXT NOT NULL,
    device        TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    result        TEXT,
    error_type    TEXT,
    error_message TEXT
);
"""

_DDL_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

# Each entry: (version, sql) — additive only (ADD COLUMN, CREATE INDEX, etc.)
_MIGRATIONS: list[tuple[int, str]] = [
    # version 1 is the baseline — handled by _DDL_V1 above
    # Future additive migrations go here, e.g.:
    # (2, "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;"),
]


class PostgresJobStore(JobStore):
    """
    Synchronous PostgreSQL JobStore backed by psycopg2.

    Uses a ThreadedConnectionPool for concurrent thread safety.
    Schema is initialised and migrated additively on first connection.
    """

    def __init__(self, dsn: Optional[str] = None):
        self._dsn = dsn or os.environ.get("DATABASE_URL", "")
        if not self._dsn:
            raise ValueError(
                "PostgresJobStore requires a DSN via the dsn argument or DATABASE_URL env var."
            )

        import psycopg2
        import psycopg2.pool
        import psycopg2.extras
        self._pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1, maxconn=10, dsn=self._dsn
        )
        self._extras = psycopg2.extras
        self._init_schema()

    def _conn(self):
        return self._pool.getconn()

    def _put(self, conn) -> None:
        self._pool.putconn(conn)

    def _init_schema(self) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Baseline table
                cur.execute(_DDL_V1)
                # Migrations tracking table
                cur.execute(_DDL_MIGRATIONS_TABLE)
                # Determine which migrations have already been applied
                cur.execute("SELECT version FROM schema_migrations;")
                applied = {row[0] for row in cur.fetchall()}
                # Apply any pending additive migrations in order
                for version, sql in _MIGRATIONS:
                    if version not in applied:
                        cur.execute(sql)
                        cur.execute(
                            "INSERT INTO schema_migrations (version) VALUES (%s);",
                            (version,),
                        )
            conn.commit()
        finally:
            self._put(conn)

    def create(self, job: Job) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs
                        (id, model_name, model_version, payload, status, device,
                         created_at, started_at, finished_at, result, error_type, error_message)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        str(job.id),
                        job.model_name,
                        job.model_version,
                        json.dumps(job.payload),
                        job.status.value,
                        job.device,
                        job.created_at,
                        job.started_at,
                        job.finished_at,
                        json.dumps(job.result) if job.result is not None else None,
                        job.error_types,
                        job.error_message,
                    ),
                )
            conn.commit()
        finally:
            self._put(conn)

    def get(self, job_id: UUID) -> Job:
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=self._extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM jobs WHERE id = %s", (str(job_id),))
                row = cur.fetchone()
        finally:
            self._put(conn)

        if not row:
            raise KeyError(f"Job {job_id} not found")

        return Job(
            id=UUID(row["id"]),
            model_name=row["model_name"],
            model_version=row["model_version"],
            payload=json.loads(row["payload"]),
            status=JobStatus(row["status"]),
            device=row["device"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
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
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = %s,
                        started_at  = COALESCE(%s, started_at),
                        finished_at = COALESCE(%s, finished_at)
                    WHERE id = %s
                    """,
                    (status.value, started_at, finished_at, str(job_id)),
                )
            conn.commit()
        finally:
            self._put(conn)

    def update_result(self, job_id: UUID, result: Any, finished_at: datetime) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET result = %s, finished_at = %s, status = %s
                    WHERE id = %s
                    """,
                    (json.dumps(result), finished_at, JobStatus.SUCCEEDED.value, str(job_id)),
                )
            conn.commit()
        finally:
            self._put(conn)

    def update_error(
        self,
        job_id: UUID,
        error_types: str,
        error_message: str,
        finished_at: datetime,
    ) -> None:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET error_type = %s, error_message = %s,
                        finished_at = %s, status = %s
                    WHERE id = %s
                    """,
                    (error_types, error_message, finished_at, JobStatus.FAILED.value, str(job_id)),
                )
            conn.commit()
        finally:
            self._put(conn)

    def close(self) -> None:
        self._pool.closeall()
