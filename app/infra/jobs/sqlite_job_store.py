import json
import sqlite3
from datetime import datetime
from uuid import UUID
from typing import Any, Optional

from app.domain.jobs import Job, JobStatus, JobStore

class SQLiteJobStore(JobStore):
    def __init__(self, db_path: str = "app/instance/jobs.db"):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
    
    def _init_schema(self):
        self._conn.execute(
            """
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
                error_message TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 1,
                last_attempt_at TEXT,
                last_retry_reason TEXT,
                max_runtime_s REAL,
                max_total_runtime_s REAL,
                cancellable INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self._conn.commit()
    
    def create(self, job: Job) -> None:
        self._conn.execute(
            """
            INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job.id),
                job.model_name,
                job.model_version,
                json.dumps(job.payload),
                job.status.value,
                job.device,
                job.created_at.isoformat(),
                job.started_at.isoformat() if job.started_at else None,
                job.finished_at.isoformat() if job.finished_at else None,
                json.dumps(job.result) if job.result is not None else None,
                job.error_types if job.error_types is not None else None,
                job.error_message if job.error_message is not None else None,
                job.attempt_count,
                job.max_attempts,
                job.last_attempt_at.isoformat() if job.last_attempt_at else None,
                job.last_retry_reason,
                job.max_runtime_s,
                job.max_total_runtime_s,
                1 if job.cancellable else 0,
            ),
        )
        self._conn.commit()
    
    def get(self, job_id: UUID) -> Job:
        row = self._conn.execute(
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
            attempt_count=row["attempt_count"],
            max_attempts=row["max_attempts"],
            last_attempt_at=datetime.fromisoformat(row["last_attempt_at"]) if row["last_attempt_at"] else None,
            last_retry_reason=row["last_retry_reason"],
            max_runtime_s=row["max_runtime_s"],
            max_total_runtime_s=row["max_total_runtime_s"],
            cancellable=bool(row["cancellable"]),
        )
    
    def update_status(self, job_id: UUID, status: JobStatus, started_at: Optional[datetime]=None, finished_at:Optional[datetime]=None) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ?, started_at = COALESCE(?, started_at), finished_at = COALESCE(?, finished_at) WHERE id = ?",
            (status.value,
            started_at.isoformat() if started_at else None,
            finished_at.isoformat() if finished_at else None,
            str(job_id)),
        )
        self._conn.commit()
    
    def update_result(self, job_id:UUID, result:Any, finished_at: datetime):
        self._conn.execute(
            """
                UPDATE jobs 
                SET result = ?, finished_at = ?, status=?
                WHERE id = ?
            """,
            (
                json.dumps(result),
                finished_at.isoformat(),
                JobStatus.SUCCEEDED.value,
                str(job_id),
            ),
        )
        self._conn.commit()
    
    def update_error(self, job_id:UUID, error_types:str, error_message:str, finished_at:datetime):
        self._conn.execute(
            """
            UPDATE jobs
            SET error_type =?, error_message = ?, finished_at = ?, status = ?
            WHERE id = ?
            """,
            (
                error_types,
                error_message,
                finished_at.isoformat(),
                JobStatus.FAILED.value,
                str(job_id)
            ),
        )
        self._conn.commit()
    
    def update_retry_metadata(
        self,
        job_id: UUID,
        attempt_count: int,
        latest_attempt_at: datetime,
        last_retry_reason: Optional[str]
    ) -> None:
        self._conn.execute(
            """
            UPDATE jobs
            SET attempt_count = ?, last_attempt_at = ?, last_retry_reason = ?
            WHERE id = ?
            """,
            (
                attempt_count,
                latest_attempt_at,
                last_retry_reason,
                str(job_id),
            ),
        )
        self._conn.commit()
    