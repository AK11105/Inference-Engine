from abc import ABC, abstractmethod
from typing import Any 

class BasePreprocessor(ABC):
    """
    Transforms raw external input to model ready input
    """
    
    @abstractmethod
    def transform(self, raw_input: Any) -> Any:
        raise NotImplementedError
    

class IdentityPreprocessor(BasePreprocessor):
    """
    No operation preprocessor
    Useful for testing and dummy models
    """
    
    def transform(self, raw_input: Any) -> Any:
        return raw_input