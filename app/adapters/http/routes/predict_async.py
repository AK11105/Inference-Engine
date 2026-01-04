from fastapi import APIRouter, Depends, Request, HTTPException
from uuid import UUID

from app.adapters.http.schemas import PredictAsyncRequest, PredictAsyncResponse, PredictAsyncStatusResponse
from app.adapters.http.deps import get_async_service
from app.security.permissions import require_scope
from app.domain.jobs.job_state import JobStatus

router = APIRouter()

@router.post("/predict/async", response_model=PredictAsyncResponse)
def submit_async(
    request: PredictAsyncRequest,
    http_request: Request,
    service = Depends(get_async_service),
):
    require_scope(http_request.state.identity, "predict")
    job_id = service.submit(
        model = request.model,
        version = request.version,
        payload = request.data,
        max_attempts=request.max_attempts,
        max_runtime_s=request.max_runtime_s,
        max_total_runtime_s=request.max_total_runtime_s,
    )
    
    return PredictAsyncResponse(job_id=str(job_id))

@router.get("/predict/async/{job_id}", response_model=PredictAsyncStatusResponse)
def get_status(
    job_id: UUID,
    http_request: Request,
    service = Depends(get_async_service),
):
    require_scope(http_request.state.identity, "predict")
    
    try:
        job = service.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job Not Found")
    
    return PredictAsyncStatusResponse(
        job_id=str(job.id),
        status=job.status.value,
        model=job.model_name,
        version=job.model_version,
        created_at=job.created_at,
        result=job.result if job.status == JobStatus.SUCCEEDED else None,
        error_message=job.error_message if job.status == JobStatus.FAILED else None,
    )