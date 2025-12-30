from typing import Any, Annotated
from pydantic import BaseModel, conlist

class PredictRequest(BaseModel):
    model: str
    version: str
    data: Any 
    
class PredictBatchRequest(BaseModel):
    model: str
    version: str
    items: conlist(Any, min_length=1)
    
class PredictAsyncRequest(BaseModel):
    model: str
    version: str
    data: Any

class PredictAsyncBatchRequest(BaseModel):
    model: str
    version: str
    items: list