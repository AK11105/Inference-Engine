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

    async def create_job(
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
        await self._store.create(job)
        await self._store.update_status(job.id, JobStatus.PENDING)
        JOB_QUEUE_DEPTH.labels(model=model_name, version=model_version).inc()
        return job.id

    async def get_job(self, job_id: UUID) -> Job:
        return await self._store.get(job_id)

    async def mark_running(self, job_id: UUID) -> None:
        job = await self._store.get(job_id)
        await self._store.update_status(job_id=job_id, status=JobStatus.RUNNING, started_at=_now())
        JOB_QUEUE_DEPTH.labels(model=job.model_name, version=job.model_version).dec()

    async def mark_succeeded(self, job_id: UUID, result: Any) -> None:
        await self._store.update_result(job_id=job_id, result=result, finished_at=_now())

    async def mark_failed(self, job_id: UUID, error_types: str, error_message: str) -> None:
        await self._store.update_error(
            job_id=job_id,
            error_types=error_types,
            error_message=error_message,
            finished_at=_now(),
        )

    async def reap_stuck(self, before: datetime) -> int:
        """Delegate to the store to mark stuck RUNNING jobs as FAILED."""
        return await self._store.reap_stuck(before=before)
