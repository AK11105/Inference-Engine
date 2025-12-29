from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.adapters.http.schemas import PredictRequest, PredictResponse
from app.services import PredictionError, PredictionService, InferenceExecutionError
from app.adapters.http.deps import get_prediction_service

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
    try:
        result = service.predict(
            model_name=request.model,
            version = request.version,
            payload=request.data,
            request_id=http_request.state.request_id,
            timeout_s=None,
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
