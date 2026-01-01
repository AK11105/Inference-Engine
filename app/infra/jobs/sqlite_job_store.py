import json
import sqlite3
from datetime import datetime
from uuid import UUID

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
                error_type TEXT,
                error_message TEXT
            )
            """
        )
        self._conn.commit()
    
    def create(self, job: Job) -> None:
        self._conn.execute(
            """
            INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job.id),
                job.model_name,
                job.model_version,
                json.dumps(job.payload),
                job.status.value,
                job.device,
                job.created_at.isoformat(),
                None,
                None,
                None,
                None,
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
            error_types=row["error_type"],
            error_message=row["error_message"],
        )
    
    def update_status(self, job_id: UUID, status: JobStatus) -> None:
        self._conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?",
            (status.value, str(job_id)),
        )
        self._conn.commit()