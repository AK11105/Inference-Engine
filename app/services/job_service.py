from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from app.domain.jobs import Job, JobStatus, JobStore
from app.core.metrics import JOB_QUEUE_DEPTH


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
            id=uuid4(),
            model_name=model_name,
            model_version=model_version,
            payload=payload,
            status=JobStatus.CREATED,
            device=device,
            created_at=_now(),
        )
        self._store.create(job)
        self._store.update_status(job.id, JobStatus.PENDING)
        JOB_QUEUE_DEPTH.labels(model=model_name, version=model_version).inc()
        return job.id

    def get_job(self, job_id: UUID) -> Job:
        return self._store.get(job_id)

    def mark_running(self, job_id: UUID) -> None:
        job = self._store.get(job_id)
        self._store.update_status(job_id=job_id, status=JobStatus.RUNNING, started_at=_now())
        JOB_QUEUE_DEPTH.labels(model=job.model_name, version=job.model_version).dec()

    def mark_succeeded(self, job_id: UUID, result: Any) -> None:
        self._store.update_result(job_id=job_id, result=result, finished_at=_now())

    def mark_failed(self, job_id: UUID, error_types: str, error_message: str) -> None:
        self._store.update_error(
            job_id=job_id,
            error_types=error_types,
            error_message=error_message,
            finished_at=_now(),
        )

    def reap_stuck(self, before: datetime) -> int:
        """Delegate to the store to mark stuck RUNNING jobs as FAILED."""
        return self._store.reap_stuck(before=before)
