from fastapi import APIRouter, Depends

from app.adapters.http.deps import get_prediction_service
from app.services import PredictionService

router = APIRouter()

@router.get("/models")
def list_models(
    service: PredictionService = Depends(get_prediction_service),
):
    """
    List all available models and versions
    Read Only, discovery endpoint
    """
    registry = service._registry
    
    models = [
        {"name": name, "version": version}
        for name, version in registry.list_models()
    ]
    
    return {"models": models}