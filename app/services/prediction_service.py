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
from app.core.tracing import get_tracer
from app.config.sla import SLA_TIMEOUTS, DEFAULT_TIMEOUT_S

logger = logging.getLogger(__name__)

_UNKNOWN_TENANT = "unknown"


class PredictionError(Exception):
    pass


class InferenceExecutionError(PredictionError):
    pass


def _resolve_timeout(model_name: str, version: str, request_timeout: float | None) -> float | None:
    """
    Return the effective timeout for a model call.

    Priority: explicit request_timeout > per-model SLA > global default.
    """
    if request_timeout is not None:
        return request_timeout
    key = f"{model_name}:{version}"
    if key in SLA_TIMEOUTS:
        return SLA_TIMEOUTS[key]
    return DEFAULT_TIMEOUT_S


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
        self._tracer = get_tracer()

    def _run_inference_with_existing_job(
        self,
        job_id,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None,
        request_id: str | None,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> Any:
        executor = self._execution_policy.resolve(model_name, version)
        effective_timeout = _resolve_timeout(model_name, version, timeout_s)
        INFERENCE_REQUESTS.labels(model_name, version, tenant_id).inc()
        start = time.time()

        with self._tracer.start_as_current_span(f"inference:{model_name}:{version}") as span:
            span.set_attribute("model", model_name)
            span.set_attribute("version", version)
            span.set_attribute("tenant_id", tenant_id)
            if request_id:
                span.set_attribute("request_id", request_id)

            try:
                pipeline = self._registry.get(model_name, version)

                def run():
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

                result = executor.submit(run, timeout_s=effective_timeout)

                latency = time.time() - start
                INFERENCE_LATENCY.labels(model_name, version, tenant_id).observe(latency)
                span.set_attribute("latency_ms", latency * 1000)

                logger.info(
                    "inference_success",
                    extra={
                        "request_id": request_id,
                        "job_id": str(job_id),
                        "model": model_name,
                        "version": version,
                        "tenant_id": tenant_id,
                        "latency_ms": latency * 1000,
                    },
                )

                return result

            except ModelNotFoundError as e:
                INFERENCE_ERRORS.labels(model_name, version, "model_not_found", tenant_id).inc()
                self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
                span.record_exception(e)
                raise PredictionError(str(e)) from e

            except ExecutionTimeoutError as e:
                INFERENCE_ERRORS.labels(model_name, version, "timeout", tenant_id).inc()
                self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
                span.record_exception(e)
                raise InferenceExecutionError(str(e)) from e

            except Exception as e:
                INFERENCE_ERRORS.labels(model_name, version, "inference_error", tenant_id).inc()
                self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
                span.record_exception(e)
                raise InferenceExecutionError(
                    f"Inference failed for model '{model_name}:{version}'"
                ) from e

    def predict(
        self,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None = None,
        request_id: str | None = None,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> Any:
        model_name, version = self._router.resolve(
            model_name, version, identity_key=request_id,
        )
        job_id = self._job_service.create_job(
            model_name=model_name, model_version=version, payload=payload,
        )
        return self._run_inference_with_existing_job(
            job_id=job_id,
            model_name=model_name,
            version=version,
            payload=payload,
            timeout_s=timeout_s,
            request_id=request_id,
            tenant_id=tenant_id,
        )

    def _run_batch_with_existing_job(
        self,
        job_id,
        model_name: str,
        version: str,
        payloads: list,
        timeout_s: float | None,
        request_id: str | None,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> list:
        executor = self._execution_policy.resolve(model_name, version)
        effective_timeout = _resolve_timeout(model_name, version, timeout_s)
        INFERENCE_REQUESTS.labels(model_name, version, tenant_id).inc()

        try:
            pipeline = self._registry.get(model_name, version)

            def run_batch():
                self._job_service.mark_running(job_id)
                try:
                    result = pipeline.run_batch(payloads)
                    self._job_service.mark_succeeded(job_id, result)
                    return result
                except Exception as e:
                    self._job_service.mark_failed(
                        job_id, error_types=type(e).__name__, error_message=str(e),
                    )
                    raise

            return executor.submit_batch(run_batch, timeout_s=effective_timeout)

        except ModelNotFoundError as e:
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found", tenant_id).inc()
            self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
            raise PredictionError(str(e)) from e

        except ExecutionTimeoutError as e:
            INFERENCE_ERRORS.labels(model_name, version, "timeout", tenant_id).inc()
            self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
            raise InferenceExecutionError(str(e)) from e

        except Exception as e:
            INFERENCE_ERRORS.labels(model_name, version, "inference_error", tenant_id).inc()
            self._job_service.mark_failed(job_id, error_types=type(e).__name__, error_message=str(e))
            raise InferenceExecutionError(
                f"Batch inference failed for model '{model_name}:{version}'"
            ) from e

    def predict_batch(
        self,
        model_name: str,
        version: str,
        payloads: list,
        timeout_s: float | None = None,
        request_id: str | None = None,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> list:
        model_name, version = self._router.resolve(
            model_name, version, identity_key=request_id,
        )
        job_id = self._job_service.create_job(
            model_name=model_name, model_version=version, payload=payloads,
        )
        return self._run_batch_with_existing_job(
            job_id=job_id,
            model_name=model_name,
            version=version,
            payloads=payloads,
            timeout_s=timeout_s,
            request_id=request_id,
            tenant_id=tenant_id,
        )
