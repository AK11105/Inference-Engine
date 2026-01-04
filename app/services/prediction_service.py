import logging
import time
from typing import Any

from app.domain.registry.registry import ModelRegistry, ModelNotFoundError
from app.execution.executor import ExecutionTimeoutError, InferenceExecutor
from app.services.routing_service import RoutingService
from app.services.job_service import JobService
from app.execution.execution_policy import ExecutionPolicy
from app.domain.jobs.job_state import JobStatus
from app.core.metrics import (
    INFERENCE_REQUESTS,
    INFERENCE_ERRORS,
    INFERENCE_LATENCY,
    INFERENCE_RETRIES,
    INFERENCE_RETRY_EXHAUSTED
)

logger = logging.getLogger(__name__)


class PredictionError(Exception):
    pass


class InferenceExecutionError(PredictionError):
    pass


class PredictionService:
    def __init__(
        self,
        registry: ModelRegistry,
        executor: InferenceExecutor,
        routing_service: RoutingService,
        execution_policy: ExecutionPolicy,
        job_service: JobService,
    ):
        self._registry = registry
        self._router = routing_service
        self._execution_policy = execution_policy
        self._job_service = job_service
    
    def _run_inference_with_existing_job(
        self,
        job_id,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None,
        request_id: str | None,
    ) -> Any:
        executor = self._execution_policy.resolve(model_name, version)
        INFERENCE_REQUESTS.labels(model_name, version).inc()
        start = time.time()
        
        try:
            pipeline = self._registry.get(model_name, version)

            def run_once():
                self._job_service.mark_running(job_id=job_id)
                try:
                    result = pipeline.run(payload)
                    self._job_service.mark_succeeded(job_id, result)
                    return result
                except Exception as e:
                    self._job_service.mark_failed(
                        job_id,
                        error_types=type(e).__name__,
                        error_message=str(e),
                    )
                    raise
            
            last_error: Exception | None = None
            while True:
                job = self._job_service.get_job(job_id=job_id)
                
                if self._job_service.is_cancelled(job):
                    raise InferenceExecutionError(f"Job {job_id} was cancelled")
                
                if not self._job_service.should_retry(job) and job.attempt_count > 0:
                    break
                
                self._job_service.record_attempt(
                    job_id=job_id, 
                    reason=(type(last_error).__name__ if last_error else "initial")
                )
                
                INFERENCE_RETRIES.labels(
                    model_name,
                    version,
                    type(last_error).__name__ if last_error else "initial",
                ).inc()
                
                effective_timeout = timeout_s
                if job.max_runtime_s is not None:
                    effective_timeout = (
                        min(timeout_s, job.max_runtime_s)
                        if timeout_s is not None
                        else job.max_runtime_s
                    )
                
                try:
                    result = executor.submit(run_once, timeout_s=effective_timeout)
                    
                    latency = time.time() - start
                    INFERENCE_LATENCY.labels(model_name, version).observe(latency)
                    
                    logger.info(
                        "inference_success",
                        extra={
                            "request_id": request_id,
                            "job_id": str(job_id),
                            "model": model_name,
                            "version": version,
                            "latency_ms": latency * 1000,
                        },
                    )
                    
                    return result
                
                except ExecutionTimeoutError as e:
                    INFERENCE_ERRORS.labels(model_name, version, "timeout").inc() #transient failure candidate
                    last_error = e
                    job = self._job_service.get_job(job_id=job_id)
                    
                    if self._job_service.has_exceeded_total_budget(job):
                        # Out of total budget: mark timeout and stop
                        self._job_service.mark_timeout(job_id, message=str(e))
                        INFERENCE_RETRY_EXHAUSTED.labels(
                            model_name,
                            version,
                            type(e).__name__,
                        ).inc()
                        break
                    
                    if not self._job_service.should_retry(job):
                        INFERENCE_RETRY_EXHAUSTED.labels(
                            model_name,
                            version,
                            type(e).__name__,
                        ).inc()
                        break
                
                except Exception as e:
                    INFERENCE_ERRORS.labels(model_name, version, "inference_error").inc()
                    last_error = e
                    break #Non-Transient / Model errors: Do not retry
                
            #If we reach here, we are out of attempts or we are chosing not to retry
            if isinstance(last_error, ExecutionTimeoutError):
                raise InferenceExecutionError(str(last_error)) from last_error
            elif last_error is not None:
                raise InferenceExecutionError(
                    f"Inference failed for model '{model_name}:{version}'"
                ) from last_error
            else:
                # Defensive fallback; should not normally happen
                raise InferenceExecutionError(
                    f"Inference failed for model '{model_name}:{version}' with unknown error"
                )
                
        except ModelNotFoundError as e:
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found").inc()
            self._job_service.mark_failed(
                job_id,
                error_types=type(e).__name__,
                error_message=str(e),
            )
            raise PredictionError(str(e)) from e

    def predict(
        self,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None = None,
        request_id: str | None = None,
        max_attempts: int | None = None,
        max_runtime_s: float | None = None,
        max_total_runtime_s: float | None = None,
    ) -> Any:
        # Resolve routing
        model_name, version = self._router.resolve(
            model_name,
            version,
            identity_key=request_id,
        )

        # Create job (Phase 9A)
        job_id = self._job_service.create_job(
            model_name=model_name,
            model_version=version,
            payload=payload,
            max_attempts=max_attempts or 3,
            max_runtime_s=max_runtime_s,
            max_total_runtime_s=max_total_runtime_s,
        )

        return self._run_inference_with_existing_job(
            job_id=job_id,
            model_name=model_name,
            version=version,
            payload=payload,
            timeout_s=timeout_s,
            request_id=request_id,
        )
    
    def _run_batch_with_existing_job(
        self,
        job_id,
        model_name: str,
        version: str,
        payloads: list,
        timeout_s: float | None,
        request_id: str | None,
    ) -> list:
        executor = self._execution_policy.resolve(model_name, version)
        INFERENCE_REQUESTS.labels(model_name, version).inc()
        
        try:
            pipeline = self._registry.get(model_name, version)
            
            def run_batch_once():
                self._job_service.mark_running(job_id)

                try:
                    result = pipeline.run_batch(payloads)
                    self._job_service.mark_succeeded(job_id, result)
                    return result
                except Exception as e:
                    self._job_service.mark_failed(
                        job_id,
                        error_types=type(e).__name__,
                        error_message=str(e),
                    )
                    raise
            
            last_error: Exception | None = None
            start = time.time()
            
            while True:
                job = self._job_service.get_job(job_id=job_id)
                
                if self._job_service.is_cancelled(job):
                    raise InferenceExecutionError(f"Job {job_id} was cancelled")

                if not self._job_service.should_retry(job) and job.attempt_count > 0:
                    break

                self._job_service.record_attempt(
                    job_id=job_id,
                    reason=(type(last_error).__name__ if last_error else "initial"),
                )
                
                INFERENCE_RETRIES.labels(
                    model_name,
                    version,
                    type(last_error).__name__ if last_error else "initial",
                ).inc()
                
                effective_timeout = timeout_s
                if job.max_runtime_s is not None:
                    effective_timeout = (
                        min(timeout_s, job.max_runtime_s)
                        if timeout_s is not None
                        else job.max_runtime_s
                    )
                
                try:
                    result = executor.submit_batch(run_batch_once, timeout_s=effective_timeout)

                    latency = time.time() - start
                    INFERENCE_LATENCY.labels(model_name, version).observe(latency)

                    logger.info(
                        "batch_inference_success",
                        extra={
                            "request_id": request_id,
                            "job_id": str(job_id),
                            "model": model_name,
                            "version": version,
                            "latency_ms": latency * 1000,
                        },
                    )

                    return result
                
                except ExecutionTimeoutError as e:
                    INFERENCE_ERRORS.labels(model_name, version, "timeout").inc()
                    last_error = e
                    job = self._job_service.get_job(job_id=job_id)
                    
                    if self._job_service.has_exceeded_total_budget(job):
                        # Out of total budget: mark timeout and stop
                        self._job_service.mark_timeout(job_id, message=str(e))
                        INFERENCE_RETRY_EXHAUSTED.labels(
                            model_name,
                            version,
                            type(e).__name__,
                        ).inc()
                        break
                    
                    if not self._job_service.should_retry(job):
                        INFERENCE_RETRY_EXHAUSTED.labels(
                            model_name,
                            version,
                            type(e).__name__,
                        ).inc()
                        break

                except Exception as e:
                    INFERENCE_ERRORS.labels(model_name, version, "inference_error").inc()
                    last_error = e
                    break  # Non-transient / model errors: do not retry
            
            # Out of attempts or chose not to retry
            if isinstance(last_error, ExecutionTimeoutError):
                raise InferenceExecutionError(str(last_error)) from last_error
            elif last_error is not None:
                raise InferenceExecutionError(
                    f"Batch inference failed for model '{model_name}:{version}'"
                ) from last_error
            else:
                raise InferenceExecutionError(
                    f"Batch inference failed for model '{model_name}:{version}' with unknown error"
                )
        
        except ModelNotFoundError as e:
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found").inc()
            self._job_service.mark_failed(
                job_id,
                error_types=type(e).__name__,
                error_message=str(e),
            )
            raise PredictionError(str(e)) from e

    def predict_batch(
        self,
        model_name: str,
        version: str,
        payloads: list,
        timeout_s: float | None = None,
        request_id: str | None = None,
        max_attempts: int | None = None,
        max_runtime_s: float | None = None,
        max_total_runtime_s: float | None = None,
    ) -> list:
        # Resolve routing
        model_name, version = self._router.resolve(
            model_name,
            version,
            identity_key=request_id,
        )

        # One job per batch (Phase 9A)
        job_id = self._job_service.create_job(
            model_name=model_name,
            model_version=version,
            payload=payloads,
            max_attempts=max_attempts or 3,
            max_runtime_s=max_runtime_s,
            max_total_runtime_s=max_total_runtime_s,
        )

        return self._run_batch_with_existing_job(
            job_id=job_id,
            model_name=model_name,
            version=version,
            payloads=payloads,
            timeout_s=timeout_s,
            request_id=request_id,
        )