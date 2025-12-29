from typing import Any 
from pydantic import BaseModel

class PredictResponse(BaseModel):
    result: Any