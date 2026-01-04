from fastapi import APIRouter, Depends, Request, HTTPException
from uuid import UUID

from app.security.permissions import require_scope
from app.adapters.http.deps import get_job_service
from app.services.job_service import JobService
from app.domain.jobs import JobStatus

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

@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: UUID,
    http_request: Request,
    job_service: JobService = Depends(get_job_service),
):
    require_scope(http_request.state.identity, "predict")
    try:
        job = job_service.get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.cancellable:
        raise HTTPException(status_code=400, detail="Job is not cancellable")

    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
        # Already finished; treat as no-op
        return {"job_id": str(job_id), "status": job.status.value}
    
    job_service.cancel_job(job_id, reason="user")
    job = job_service.get_job(job_id)

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "error_message": job.error_message,
    }
    