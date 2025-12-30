from typing import Any, Annotated, Optional
from pydantic import BaseModel, conlist

class PredictRequest(BaseModel):
    model: str
    version: Optional[str] = None
    data: Any 
    
class PredictBatchRequest(BaseModel):
    model: str
    version: Optional[str] = None
    items: conlist(Any, min_length=1)
    
class PredictAsyncRequest(BaseModel):
    model: str
    version: Optional[str] = None
    data: Any

class PredictAsyncBatchRequest(BaseModel):
    model: str
    version: Optional[str] = None
    items: list