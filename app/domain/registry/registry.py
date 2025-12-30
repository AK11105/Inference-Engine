from typing import Dict, Tuple, List

from app.domain.pipelines import InferencePipeline
from app.domain.definitions import echo_v1, echo_v2

class ModelNotFoundError(Exception):
    pass

class ModelRegistry:
    """
    Resolves (model_name, version) -> InferencePipeline
    with lazy loading and in-memory caching
    """
    
    def __init__(self):
        self._pipelines: Dict[Tuple[str, str], InferencePipeline] = {}
        self._definitions = {
            (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
            (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline
        }
    
    def get(self, model_name: str, version: str) -> InferencePipeline:
        key = (model_name, version)
        if key in self._pipelines:
            return self._pipelines[key]
        
        if key not in self._definitions:
            raise ModelNotFoundError(
                f"Model '{model_name}' with version '{version}' not found."
            )
        
        pipeline = self._definitions[key]()
        self._pipelines[key] = pipeline
        return pipeline
    
    def list_models(self) -> List[Tuple[str, str]]:
        """
        Return all available (model_name, version) pairs.
        """
        return list(self._definitions.keys())