"""
PostgreSQL-backed JobStore using asyncpg (non-blocking, event-loop safe).

Schema changes are applied as additive ALTER TABLE statements — columns are
never dropped, so existing job history is preserved across upgrades.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import asyncpg

from app.domain.jobs import Job, JobStatus, JobStore

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

_MIGRATIONS: list[tuple[int, str]] = []


class PostgresJobStore(JobStore):
    """
    Async PostgreSQL JobStore backed by asyncpg connection pool.

    Call `await PostgresJobStore.create_pool(dsn)` to get an initialised instance.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def create_pool(cls, dsn: Optional[str] = None) -> "PostgresJobStore":
        dsn = dsn or os.environ.get("DATABASE_URL", "")
        if not dsn:
            raise ValueError(
                "PostgresJobStore requires a DSN via the dsn argument or DATABASE_URL env var."
            )
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        store = cls(pool)
        await store._init_schema()
        return store

    async def _init_schema(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(_DDL_V1)
            await conn.execute(_DDL_MIGRATIONS_TABLE)
            applied = {
                row["version"]
                for row in await conn.fetch("SELECT version FROM schema_migrations;")
            }
            for version, sql in _MIGRATIONS:
                if version not in applied:
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES ($1);", version
                    )

    async def create(self, job: Job) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO jobs
                    (id, model_name, model_version, payload, status, device,
                     created_at, started_at, finished_at, result, error_type, error_message)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
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
            )

    async def get(self, job_id: UUID) -> Job:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", str(job_id))

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

    async def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE jobs
                SET status = $1,
                    started_at  = COALESCE($2, started_at),
                    finished_at = COALESCE($3, finished_at)
                WHERE id = $4
                """,
                status.value, started_at, finished_at, str(job_id),
            )

    async def update_result(self, job_id: UUID, result: Any, finished_at: datetime) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET result = $1, finished_at = $2, status = $3 WHERE id = $4",
                json.dumps(result), finished_at, JobStatus.SUCCEEDED.value, str(job_id),
            )

    async def update_error(
        self,
        job_id: UUID,
        error_types: str,
        error_message: str,
        finished_at: datetime,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE jobs
                SET error_type = $1, error_message = $2,
                    finished_at = $3, status = $4
                WHERE id = $5
                """,
                error_types, error_message, finished_at, JobStatus.FAILED.value, str(job_id),
            )

    async def close(self) -> None:
        await self._pool.close()

    async def reap_stuck(self, before: datetime) -> int:
        """Mark RUNNING jobs whose started_at is before `before` as FAILED."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE jobs
                SET status = $1,
                    error_message = 'reaped: worker did not complete in time',
                    finished_at = $2
                WHERE status = $3 AND started_at < $4
                """,
                JobStatus.FAILED.value,
                datetime.now(timezone.utc),
                JobStatus.RUNNING.value,
                before,
            )
        # asyncpg returns "UPDATE N" as a string
        return int(result.split()[-1])
