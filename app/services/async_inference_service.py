from typing import Any
from uuid import UUID

from app.services.prediction_service import PredictionService
from app.services.job_service import JobService
from app.domain.jobs.job import Job


class AsyncInferenceService:
    """
    Async wrapper over PredictionService.

    - Does NOT own jobs
    - Does NOT store state in memory
    - Delegates job lifecycle to JobService + PredictionService
    """

    def __init__(
        self,
        prediction_service: PredictionService,
    ):
        self._service = prediction_service
        self._job_service = prediction_service._job_service

    def submit(
        self,
        model: str,
        version: str,
        payload: Any,
        max_attempts: int | None = None,
        max_runtime_s: float | None = None,
        max_total_runtime_s: float | None = None,
    ) -> UUID:
        """
        Fire-and-forget inference.
        Returns job_id immediately.
        """

        # Create job using the SAME path as sync
        job_id = self._job_service.create_job(
            model_name=model,
            model_version=version,
            payload=payload,
            max_attempts=max_attempts or 3,
            max_runtime_s=max_runtime_s,
            max_total_runtime_s=max_total_runtime_s,
        )

        executor = self._service._execution_policy.resolve(model, version)

        def run():
            # predict() will handle all job transitions
            self._service._run_inference_with_existing_job(
                job_id=job_id,
                model_name=model,
                version=version,
                payload=payload,
                timeout_s=None,
                request_id=None,
            )

        executor.submit_background(run)
        return job_id

    def submit_batch(
        self,
        model: str,
        version: str,
        payloads: list,
        max_attempts: int | None = None,
        max_runtime_s: float | None = None,
        max_total_runtime_s: float | None = None,
    ) -> UUID:
        job_id = self._job_service.create_job(
            model_name=model,
            model_version=version,
            payload=payloads,
            max_attempts=max_attempts or 3,
            max_runtime_s=max_runtime_s,
            max_total_runtime_s=max_total_runtime_s,
        )

        executor = self._service._execution_policy.resolve(model, version)

        def run():
            self._service._run_batch_with_existing_job(
                job_id=job_id,
                model_name=model,
                version=version,
                payloads=payloads,
                timeout_s=None,
                request_id=None,
            )

        executor.submit_background(run)
        return job_id

    def get(self, job_id: UUID) -> Job:
        """
        Read job state from persistent store.
        """
        return self._job_service.get_job(job_id)
