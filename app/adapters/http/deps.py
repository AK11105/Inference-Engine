from app.domain.registry import ModelRegistry
from app.services import PredictionService

def get_registry() -> ModelRegistry:
    # One Registry per process
    return ModelRegistry()

def get_prediction_service() -> PredictionService:
    registry = get_registry()
    return PredictionService(registry)