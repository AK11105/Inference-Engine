from typing import Any, Annotated, Optional
from pydantic import BaseModel, conlist

class PredictRequest(BaseModel):
    model: str
    version: Optional[str] = None
    data: Any 
    
    # 9C/9D controls (optional)
    max_attempts: Optional[int] = None
    max_runtime_s: Optional[float] = None          # per-attempt budget
    max_total_runtime_s: Optional[float] = None    # across attempts
    
class PredictBatchRequest(BaseModel):
    model: str
    version: Optional[str] = None
    items: conlist(Any, min_length=1)
    
    max_attempts: Optional[int] = None
    max_runtime_s: Optional[float] = None
    max_total_runtime_s: Optional[float] = None
    
class PredictAsyncRequest(BaseModel):
    model: str
    version: Optional[str] = None
    data: Any
    
    max_attempts: Optional[int] = None
    max_runtime_s: Optional[float] = None
    max_total_runtime_s: Optional[float] = None

class PredictAsyncBatchRequest(BaseModel):
    model: str
    version: Optional[str] = None
    items: list
    
    max_attempts: Optional[int] = None
    max_runtime_s: Optional[float] = None
    max_total_runtime_s: Optional[float] = None