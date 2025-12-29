from abc import ABC, abstractmethod
from typing import Any, Iterable

class BaseModel(ABC):
    """
    Pure inference model abstraction
    """
    @abstractmethod
    def load(self) -> None:
        """
        Load model artifacts into memory
        Called once before inference
        """
        raise NotImplementedError
    
    @abstractmethod
    def predict(self, x: Any) -> Any:
        """
        Run Inference on a single input
        """ 
        raise NotImplementedError
    
    def predict_batch(self, xs: Iterable[Any]) -> list[Any]:
        """
        Batch Inference 
        Naive implementation for now
        """
        return [self.predict(x) for x in xs]