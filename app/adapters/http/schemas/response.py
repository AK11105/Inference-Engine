from typing import Any , List, Optional
from pydantic import BaseModel
from datetime import datetime

class PredictResponse(BaseModel):
    result: Any

class PredictBatchResponse(BaseModel):
    results: List[Any]

class PredictAsyncResponse(BaseModel):
    job_id: str

class PredictAsyncStatusResponse(BaseModel):
    job_id: str
    status: str
    model: str
    version: str
    created_at: datetime
    result: Optional[Any] = None          
    error_message: Optional[str] = None
