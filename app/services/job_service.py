from datetime import datetime
from uuid import UUID, uuid4

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
    ) -> UUID:
        job = Job(
            id =uuid4(),
            model_name=model_name,
            model_version=model_version,
            payload=payload,
            status=JobStatus.CREATED,
            device=device,
            created_at=datetime.utcnow(),
        )
        
        self._store.create(job)
        self._store.update_status(job.id, JobStatus.PENDING)
        return job.id
    
    def get_job(self, job_id: UUID) -> Job:
        return self._store.get(job_id)