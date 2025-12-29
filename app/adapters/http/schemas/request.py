from typing import Any
from pydantic import BaseModel

class PredictRequest(BaseModel):
    model: str
    version: str
    data: Any 