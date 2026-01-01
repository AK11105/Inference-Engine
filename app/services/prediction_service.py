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

    def predict(
        self,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None = None,
        request_id: str | None = None,
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
        )

        executor = self._execution_policy.resolve(model_name, version)
        INFERENCE_REQUESTS.labels(model_name, version).inc()
        start = time.time()

        try:
            pipeline = self._registry.get(model_name, version)

            def run():
                self._job_service._store.update_status(job_id, JobStatus.RUNNING)
                try:
                    result = pipeline.run(payload)
                    self._job_service._store.update_status(job_id, JobStatus.SUCCEEDED)
                    return result
                except Exception:
                    self._job_service._store.update_status(job_id, JobStatus.FAILED)
                    raise

            result = executor.submit(
                run,
                timeout_s=timeout_s,
            )

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

        except ModelNotFoundError as e:
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise PredictionError(str(e)) from e

        except ExecutionTimeoutError as e:
            INFERENCE_ERRORS.labels(model_name, version, "timeout").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise InferenceExecutionError(str(e)) from e

        except Exception as e:
            INFERENCE_ERRORS.labels(model_name, version, "inference_error").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise InferenceExecutionError(
                f"Inference failed for model '{model_name}:{version}'"
            ) from e

    def predict_batch(
        self,
        model_name: str,
        version: str,
        payloads: list,
        timeout_s: float | None = None,
        request_id: str | None = None,
    ) -> list:
        # Resolve routing
        model_name, version = self._router.resolve(
            model_name,
            version,
            identity_key=request_id,
        )
        logger.info(f"🔍 routing OK: {model_name}:{version}")

        # One job per batch (Phase 9A)
        job_id = self._job_service.create_job(
            model_name=model_name,
            model_version=version,
            payload=payloads,
        )
        logger.info(f"🔍 job created: {job_id}")

        executor = self._execution_policy.resolve(model_name, version)
        INFERENCE_REQUESTS.labels(model_name, version).inc(len(payloads))

        try:
            pipeline = self._registry.get(model_name, version)
            logger.info(f"🔍 pipeline loaded: {type(pipeline)}")

            def run_batch():
                logger.info("🔍 run_batch executing...")
                self._job_service._store.update_status(job_id, JobStatus.RUNNING)
                try:
                    result = pipeline.run_batch(payloads)
                    self._job_service._store.update_status(job_id, JobStatus.SUCCEEDED)
                    logger.info(f"🔍 run_batch result len: {len(result)}")
                    return result
                except Exception:
                    self._job_service._store.update_status(job_id, JobStatus.FAILED)
                    raise
            
            result = executor.submit_batch(run_batch, timeout_s=timeout_s,)
            logger.info("🔍 executor success!")
            return result
        
        except ModelNotFoundError as e:  # ✅ Add this!
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise PredictionError(str(e)) from e

        except ExecutionTimeoutError as e:
            INFERENCE_ERRORS.labels(model_name, version, "timeout").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise InferenceExecutionError(str(e)) from e

        except Exception as e:
            INFERENCE_ERRORS.labels(model_name, version, "inference_error").inc()
            self._job_service._store.update_status(job_id, JobStatus.FAILED)
            raise InferenceExecutionError(
                f"Batch inference failed for model '{model_name}:{version}'"
            ) from e
