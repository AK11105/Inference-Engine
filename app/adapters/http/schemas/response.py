from typing import Any , List
from pydantic import BaseModel

class PredictResponse(BaseModel):
    result: Any

class PredictBatchResponse(BaseModel):
    results: List[Any]

class PredictAsyncResponse(BaseModel):
    job_id: str

class PredictAsyncStatusResponse(BaseModel):
    status: str
    result: Any | None = None
    error: str | None = None 