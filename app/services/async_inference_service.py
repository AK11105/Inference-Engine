import asyncio
from typing import Any
from uuid import UUID

from app.services.prediction_service import PredictionService
from app.services.job_service import JobService
from app.domain.jobs.job import Job


class AsyncInferenceService:
    def __init__(self, prediction_service: PredictionService, job_queue=None):
        self._service = prediction_service
        self._job_service: JobService = prediction_service._job_service
        self._queue = job_queue

    async def submit(self, model: str, version: str, payload: Any) -> UUID:
        job_id = self._job_service.create_job(
            model_name=model, model_version=version, payload=payload,
        )
        if self._queue is not None:
            await self._queue.enqueue_inference(job_id, model, version, payload)
        else:
            self._fallback_submit(job_id, model, version, payload)
        return job_id

    async def submit_batch(self, model: str, version: str, payloads: list) -> UUID:
        job_id = self._job_service.create_job(
            model_name=model, model_version=version, payload=payloads,
        )
        if self._queue is not None:
            await self._queue.enqueue_batch_inference(job_id, model, version, payloads)
        else:
            self._fallback_submit_batch(job_id, model, version, payloads)
        return job_id

    def get(self, job_id: UUID) -> Job:
        return self._job_service.get_job(job_id)

    def _fallback_submit(self, job_id: UUID, model: str, version: str, payload: Any) -> None:
        executor = self._service._execution_policy.resolve(model, version)
        registry = self._service._registry
        job_service = self._job_service

        def run():
            job_service.mark_running(job_id)
            try:
                result = registry.get(model, version).run(payload)
                job_service.mark_succeeded(job_id, result)
            except Exception as exc:
                job_service.mark_failed(job_id, type(exc).__name__, str(exc))

        executor.submit_background(run)

    def _fallback_submit_batch(self, job_id: UUID, model: str, version: str, payloads: list) -> None:
        executor = self._service._execution_policy.resolve(model, version)
        registry = self._service._registry
        job_service = self._job_service

        def run():
            job_service.mark_running(job_id)
            try:
                result = registry.get(model, version).run_batch(payloads)
                job_service.mark_succeeded(job_id, result)
            except Exception as exc:
                job_service.mark_failed(job_id, type(exc).__name__, str(exc))

        executor.submit_background(run)
