from fastapi import APIRouter, Depends, Request, HTTPException

from app.adapters.http.deps import get_prediction_service
from app.services import PredictionService
from app.security.permissions import require_scope

router = APIRouter()

@router.get("/debug/models/loaded")
def loaded_models(
    http_request: Request,
    service: PredictionService = Depends(get_prediction_service),
):
    try:
        require_scope(http_request.state.identity, "admin")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    registry = service._registry
    loaded = [
        {"name": name, "version": version}
        for (name, version) in registry._pipelines.keys()
    ]
    return {"loaded_models": loaded}