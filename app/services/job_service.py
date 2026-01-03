from datetime import datetime
from uuid import UUID, uuid4
from typing import Any, Optional

from app.domain.jobs import Job, JobStatus, JobStore


class JobService:
    def __init__(self, store: JobStore):
        self._store = store
        
    def create_job(
        self,
        model_name: str,
        model_version: str,
        payload,
        device: str = "cpu",
        max_attempts: int = 1,
    ) -> UUID:
        job = Job(
            id =uuid4(),
            model_name=model_name,
            model_version=model_version,
            payload=payload,
            status=JobStatus.CREATED,
            device=device,
            created_at=datetime.utcnow(),
            attempt_count=0,
            max_attempts=max_attempts,
        )
        
        self._store.create(job)
        self._store.update_status(job.id, JobStatus.PENDING)
        return job.id
    
    def get_job(self, job_id: UUID) -> Job:
        return self._store.get(job_id)
    
    def mark_running(self, job_id: UUID) -> None:
        self._store.update_status(
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
    
    def mark_succeeded(self, job_id: UUID, result: Any) -> None:
        self._store.update_result(
            job_id=job_id,
            result=result,
            finished_at=datetime.utcnow(),
        )
    
    def mark_failed(self, job_id: UUID, error_types: str, error_message: str) -> None:
        self._store.update_error(
            job_id=job_id,
            error_types=error_types,
            error_message=error_message,
            finished_at=datetime.utcnow(),
        )
    
    def should_retry(self, job: Job) -> bool:
        return job.attempt_count < job.max_attempts
    
    def record_attempt(self, job_id: UUID, reason: Optional[str] = None,) -> Job:
        job = self.get_job(job_id=job_id)
        new_attempt_count = job.attempt_count + 1
        now = datetime.utcnow()
        
        self._store.update_retry_metadata(
            job_id=job_id,
            attempt_count=new_attempt_count,
            latest_attempt_at=now,
            last_retry_reason=reason,
        )
        
        return self.get_job(job_id=job_id)