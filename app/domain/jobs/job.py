from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.domain.jobs.job_state import JobStatus

@dataclass
class Job:
    id: UUID
    model_name: str
    model_version: str
    payload: Any
    
    status: JobStatus
    device: str
    
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    
    result: Optional[Any] = None 
    error_types: Optional[str] = None
    error_message: Optional[str] = None
    
    attempt_count: int = 0
    max_attempts: int = 1
    last_attempt_at: datetime | None = None
    last_retry_reason: str | None = None
    
    max_runtime_s: float | None = None
    max_total_runtime_s: float | None = None
    cancellable: bool = True