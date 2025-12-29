from typing import Any

from app.domain.registry import ModelNotFoundError, ModelRegistry

class PredictionError(Exception):
    """
    Base Class for all prediction-related errors
    """
    pass

class InferenceExecutionError(PredictionError):
    """
    Raised when model inference fails at runtime
    """
    pass

class PredictionService:
    """
    Orchestrate Inference Use-Case
    
    This service:
    - owns model selection
    - owns error translation
    - hides registry and pipeline details from callers
    """
    
    def __init__(self, registry: ModelRegistry):
        self._registry = registry
        
    def predict(
        self,
        model_name: str,
        version: str,
        payload: Any,
    ) -> Any:
        """
        Execute inference for a given model identity and payload.
        """
        
        try:
            pipeline = self._registry.get(model_name, version)
        except ModelNotFoundError as e:
            #Re-raise as a service-level error
            raise PredictionError(str(e)) from e
        
        try:
            return pipeline.run(payload)
        except Exception as e:
            #Catch model-level failures and normalize
            raise InferenceExecutionError(
                f"Inference failed for model '{model_name}:{version}'"
            ) from e