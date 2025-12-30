from functools import lru_cache

from app.domain.registry import ModelRegistry
from app.services import PredictionService, AsyncInferenceService
from app.execution import InferenceExecutor

@lru_cache
def get_registry() -> ModelRegistry:
    # One Registry per process
    return ModelRegistry()

@lru_cache
def get_executor() -> InferenceExecutor:
    return InferenceExecutor(max_workers=4, default_timeout_s=10.0)

def get_prediction_service() -> PredictionService:
    registry = get_registry()
    executor = get_executor()
    return PredictionService(registry, executor)

@lru_cache
def get_async_service() -> AsyncInferenceService:
    return AsyncInferenceService(get_prediction_service())