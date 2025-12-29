import logging
import time
from typing import Any

from app.domain.registry.registry import ModelRegistry, ModelNotFoundError
from app.execution.executor import InferenceExecutor, ExecutionTimeoutError
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
    def __init__(self, registry: ModelRegistry, executor: InferenceExecutor):
        self._registry = registry
        self._executor = executor

    def predict(
        self,
        model_name: str,
        version: str,
        payload: Any,
        timeout_s: float | None = None,
        request_id: str | None = None,
    ) -> Any:
        INFERENCE_REQUESTS.labels(model_name, version).inc()
        start = time.time()

        try:
            pipeline = self._registry.get(model_name, version)
            result = self._executor.submit(
                pipeline.run,
                payload,
                timeout_s=timeout_s,
            )

            latency = time.time() - start
            INFERENCE_LATENCY.labels(model_name, version).observe(latency)

            logger.info(
                "inference_success",
                extra={
                    "request_id": request_id,
                    "model": model_name,
                    "version": version,
                    "latency_ms": latency * 1000,
                },
            )

            return result

        except ModelNotFoundError as e:
            INFERENCE_ERRORS.labels(model_name, version, "model_not_found").inc()
            raise PredictionError(str(e)) from e

        except ExecutionTimeoutError as e:
            INFERENCE_ERRORS.labels(model_name, version, "timeout").inc()
            raise InferenceExecutionError(str(e)) from e

        except Exception as e:
            INFERENCE_ERRORS.labels(model_name, version, "inference_error").inc()
            raise InferenceExecutionError(
                f"Inference failed for model '{model_name}:{version}'"
            ) from e
