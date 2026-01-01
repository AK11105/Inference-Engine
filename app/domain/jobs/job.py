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
    
    error_types: Optional[str] = None
    error_message: Optional[str] = None