from fastapi import APIRouter, Depends
from uuid import UUID

from app.adapters.http.deps import get_job_service
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])

@router.get("/{job_id}")
def get_job(job_id: UUID, service: JobService = Depends(get_job_service)):
    job = service.get_job(job_id)
    return {
        "job_id": str(job.id),
        "status": job.status,
        "model": job.model_name,
        "version": job.model_version,
        "created_at": job.created_at,
    }