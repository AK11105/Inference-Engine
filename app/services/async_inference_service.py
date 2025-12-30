import uuid
from enum import Enum
from typing import Any, Dict
from threading import Lock

from app.services.prediction_service import PredictionService

class JobStatus(str, Enum):
    PENDING = "pending",
    RUNNING = "running",
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    
class AsyncJob:
    def __init__(self):
        self.status = JobStatus.PENDING
        self.result: Any | None = None
        self.error: str | None = None

class AsyncInferenceService:
    """
    Manages Async Inference Jobs
    """
    def __init__(self, prediction_service: PredictionService):
        self._service = prediction_service
        self._jobs : Dict[str, AsyncJob] = {}
        self._lock = Lock()
        
    def submit(
        self, 
        model: str,
        version: str,
        payload: Any,
    ) -> Any:
        job_id = str(uuid.uuid4())
        job = AsyncJob()
        
        with self._lock:
            self._jobs[job_id] = job
        
        def run():
            job.status = JobStatus.RUNNING
            try:
                job.result = self._service.predict(
                    model_name=model,
                    version=version,
                    payload=payload
                )
                job.status = JobStatus.SUCCEEDED
            except Exception as e:
                job.error = str(e)
                job.status = JobStatus.FAILED
                
        #Fire and Forget
        executor = self._service._execution_policy.resolve(model, version)
        executor.submit_background(run)

        
        return job_id
    
    def get(self, job_id: str) -> AsyncJob:
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError("Job Not Found")
        return job
    
    def submit_batch(
        self,
        model: str,
        version: str,
        payloads: list,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = AsyncJob()
        
        with self._lock:
            self._jobs[job_id] = job
        
        def run():
            job.status = JobStatus.RUNNING
            try:
                job.result = self._service.predict_batch(
                    model_name=model,
                    version=version,
                    payloads=payloads,
                )
                job.status = JobStatus.SUCCEEDED
            except Exception as e:
                job.error = str(e)
                job.status = JobStatus.FAILED
        
        #background execution (respect executor boundary)
        executor = self._service._execution_policy.resolve(model, version)
        executor.submit_background(run)

        
        return job_id