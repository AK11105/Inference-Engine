from fastapi import APIRouter, Depends
from fastapi import Request

from app.adapters.http.deps import get_prediction_service
from app.services import PredictionService
from app.security.permissions import require_scope

router = APIRouter()

@router.get("/models")
def list_models(
    http_request: Request,
    service: PredictionService = Depends(get_prediction_service),
):
    """
    List all available models and versions
    Read Only, discovery endpoint
    """
    require_scope(http_request.state.identity, "read_models")
    registry = service._registry
    
    models = [
        {"name": name, "version": version}
        for name, version in registry.list_models()
    ]
    
    return {"models": models}