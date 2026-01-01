from fastapi import APIRouter, Depends, Request, HTTPException

from app.adapters.http.schemas import PredictAsyncRequest, PredictAsyncResponse, PredictAsyncStatusResponse
from app.adapters.http.deps import get_async_service
from app.security.permissions import require_scope

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
    )
    
    return PredictAsyncResponse(job_id=str(job_id))

@router.get("/predict/async/{job_id}", response_model=PredictAsyncStatusResponse)
def get_status(
    job_id: str,
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
        status=job.status,
        model=job.model_name,
        version=job.model_version,
        created_at=job.created_at,
    )