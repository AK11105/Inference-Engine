from abc import ABC, abstractmethod
from uuid import UUID
from typing import Any, Optional
from datetime import datetime

from app.domain.jobs.job import Job
from app.domain.jobs.job_state import JobStatus


class JobStore(ABC):
    @abstractmethod
    async def create(self, job: Job) -> None: ...

    @abstractmethod
    async def get(self, job_id: UUID) -> Job: ...

    @abstractmethod
    async def update_status(
        self,
        job_id: UUID,
        status: JobStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None: ...

    @abstractmethod
    async def update_result(self, job_id: UUID, result: Any, finished_at: datetime) -> None: ...

    @abstractmethod
    async def update_error(
        self, job_id: UUID, error_types: str, error_message: str, finished_at: datetime
    ) -> None: ...

    @abstractmethod
    async def reap_stuck(self, before: datetime) -> int:
        """Mark RUNNING jobs started before `before` as FAILED. Returns count reaped."""
        ...
