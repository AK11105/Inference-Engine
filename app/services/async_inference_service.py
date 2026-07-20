import asyncio
import logging as _log
import time
from typing import Any
from uuid import UUID

from app.services.prediction_service import PredictionService
from app.services.job_service import JobService
from app.domain.jobs.job import Job
from app.core.logging import get_logger

_UNKNOWN_TENANT = "unknown"
_COMPONENT = "AsyncInferenceService"
logger = get_logger(__name__)


class AsyncInferenceService:
    def __init__(self, prediction_service: PredictionService, job_queue=None):
        self._service = prediction_service
        self._job_service: JobService = prediction_service._job_service
        self._queue = job_queue

    async def submit(
        self, model: str, version: str, payload: Any,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> UUID:
        job_id = await self._job_service.create_job(
            model_name=model, model_version=version, payload=payload,
        )
        logger.info(
            event="AsyncJobQueued", component=_COMPONENT,
            job_id=str(job_id), model_id=model, version=version,
        )
        if self._queue is not None:
            await self._queue.enqueue_inference(job_id, model, version, payload)
        else:
            asyncio.create_task(
                self._fallback_run(job_id, model, version, payload, tenant_id)
            )
        return job_id

    async def submit_batch(
        self, model: str, version: str, payloads: list,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> UUID:
        job_id = await self._job_service.create_job(
            model_name=model, model_version=version, payload=payloads,
        )
        logger.info(
            event="AsyncJobQueued", component=_COMPONENT,
            job_id=str(job_id), model_id=model, version=version,
        )
        if self._queue is not None:
            await self._queue.enqueue_batch_inference(job_id, model, version, payloads)
        else:
            asyncio.create_task(
                self._fallback_run_batch(job_id, model, version, payloads, tenant_id)
            )
        return job_id

    async def get(self, job_id: UUID) -> Job:
        return await self._job_service.get_job(job_id)

    async def _fallback_run(
        self, job_id: UUID, model: str, version: str, payload: Any,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> None:
        executor = self._service._execution_policy.resolve(model, version)
        registry = self._service._registry
        job_service = self._job_service

        await job_service.mark_running(job_id)
        logger.info(event="AsyncJobStarted", component=_COMPONENT, job_id=str(job_id))
        start = time.time()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor._executor, lambda: registry.get(model, version).run(payload)
            )
            await job_service.mark_succeeded(job_id, result)
            logger.info(
                event="AsyncJobCompleted", component=_COMPONENT,
                job_id=str(job_id), latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            _log.getLogger(__name__).error("async job %s failed: %s", job_id, exc, exc_info=True)
            logger.error(
                event="AsyncJobFailed", component=_COMPONENT,
                job_id=str(job_id), error=str(exc),
            )
            try:
                await job_service.mark_failed(job_id, type(exc).__name__, str(exc))
            except Exception:
                pass

    async def _fallback_run_batch(
        self, job_id: UUID, model: str, version: str, payloads: list,
        tenant_id: str = _UNKNOWN_TENANT,
    ) -> None:
        executor = self._service._execution_policy.resolve(model, version)
        registry = self._service._registry
        job_service = self._job_service

        await job_service.mark_running(job_id)
        logger.info(event="AsyncJobStarted", component=_COMPONENT, job_id=str(job_id))
        start = time.time()
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                executor._executor, lambda: registry.get(model, version).run_batch(payloads)
            )
            await job_service.mark_succeeded(job_id, result)
            logger.info(
                event="AsyncJobCompleted", component=_COMPONENT,
                job_id=str(job_id), latency_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            _log.getLogger(__name__).error(
                "async batch job %s failed: %s", job_id, exc, exc_info=True
            )
            logger.error(
                event="AsyncJobFailed", component=_COMPONENT,
                job_id=str(job_id), error=str(exc),
            )
            try:
                await job_service.mark_failed(job_id, type(exc).__name__, str(exc))
            except Exception:
                pass
