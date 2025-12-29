from typing import Any 

from app.domain.models import BaseModel

class EchoModel(BaseModel):
    """
    Dummy Model to validate inference flow
    """
    def load(self) -> None:
        pass #No artifacts to load
    
    def predict(self, x: Any) -> Any:
        return {
            "echo": x
        }