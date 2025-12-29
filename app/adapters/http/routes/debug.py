from fastapi import APIRouter, Depends

from app.adapters.http.deps import get_prediction_service
from app.services import PredictionService

router = APIRouter()

@router.get("/debug/models/loaded")
def loaded_models(
    service: PredictionService = Depends(get_prediction_service),
):
    registry = service._registry
    loaded = [
        {"name": name, "version": version}
        for (name, version) in registry._pipelines.keys()
    ]
    return {"loaded_models": loaded}