from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.adapters.http.schemas import PredictRequest, PredictResponse
from app.services import PredictionError, PredictionService, InferenceExecutionError
from app.adapters.http.deps import get_prediction_service
from app.security.permissions import require_scope

router = APIRouter()

@router.post(
    "/predict",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
)
def predict(
    request: PredictRequest,
    http_request: Request,
    service: PredictionService = Depends(get_prediction_service),
):
    require_scope(http_request.state.identity, "predict")
    try:
        result = service.predict(
            model_name=request.model,
            version = request.version,
            payload=request.data,
            request_id=http_request.state.request_id,
            timeout_s=None,
            max_attempts=request.max_attempts,
            max_runtime_s=request.max_runtime_s,
            max_total_runtime_s=request.max_total_runtime_s,
        )
        return PredictResponse(result=result)
    except InferenceExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    except PredictionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
