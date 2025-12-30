from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.http.schemas import PredictBatchResponse, PredictBatchRequest
from app.adapters.http.deps import get_prediction_service
from app.services.prediction_service import PredictionError, PredictionService, InferenceExecutionError
from app.security.permissions import require_scope

router = APIRouter()

@router.post("/predict/batch", response_model=PredictBatchResponse)
def predict_batch(
    request: PredictBatchRequest,
    http_request: Request,
    service: PredictionService = Depends(get_prediction_service),
):
    try:
        require_scope(http_request.state.identity, "predict")
        results = service.predict_batch(
            model_name=request.model,
            version=request.version,
            payloads=request.items,
            request_id=http_request.state.request_id,
        )
        
        return PredictBatchResponse(results=results)
    
    except InferenceExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except PredictionError as e:
        raise HTTPException(status_code=400, detail=str(e))