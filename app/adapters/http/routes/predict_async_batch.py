from fastapi import APIRouter, Depends, Request, HTTPException

from app.adapters.http.schemas import PredictAsyncBatchRequest, PredictAsyncResponse, PredictAsyncStatusResponse
from app.adapters.http.deps import get_async_service
from app.security.permissions import require_scope

router = APIRouter()

@router.post("/predict/async/batch", response_model=PredictAsyncResponse)
def submit_async_batch(
    request: PredictAsyncBatchRequest,
    http_request: Request,
    service = Depends(get_async_service),
):
    require_scope(http_request.state.identity, "predict")
    job_id = service.submit_batch(
        model = request.model,
        version = request.version,
        payloads = request.items,
        max_attempts=request.max_attempts,
        max_runtime_s=request.max_runtime_s,
        max_total_runtime_s=request.max_total_runtime_s,
    )
    
    return PredictAsyncResponse(job_id = str(job_id))