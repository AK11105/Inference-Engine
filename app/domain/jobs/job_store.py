from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.jobs.job import Job
from app.domain.jobs.job_state import JobStatus

class JobStore(ABC):
    @abstractmethod
    def create(self, job:Job) -> None:
        ...
    
    @abstractmethod
    def get(self, job_id: UUID) -> Job:
        ...
    
    @abstractmethod
    def update_status(self, job_id: UUID, status: JobStatus) -> None:
        ...