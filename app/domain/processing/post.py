from abc import ABC, abstractmethod
from typing import Any 

class BasePostprocessor(ABC):
    """
    Transforms model output to response-ready output
    """
    @abstractmethod
    def transform(self, model_output: Any) -> Any:
        raise NotImplementedError
    
class IdentityPostprocessor(BasePostprocessor):
    """
    No operation post processor
    Useful for testing and dummy models
    """
    
    def transform(self, model_output: Any) -> Any:
        return model_output 

