from functools import lru_cache

from app.domain.registry import ModelRegistry
from app.services import PredictionService, AsyncInferenceService
from app.execution import InferenceExecutor
from app.services.routing_service import RoutingService
from app.config.routing import ROUTES
from app.execution.execution_policy import ExecutionPolicy
from app.config.execution import EXECUTION_POLICY, DEFAULT_EXECUTOR
from app.infra.jobs.sqlite_job_store import SQLiteJobStore
from app.services.job_service import JobService


@lru_cache
def get_registry() -> ModelRegistry:
    return ModelRegistry()


@lru_cache
def get_job_store() -> SQLiteJobStore:
    return SQLiteJobStore()


@lru_cache
def get_job_service() -> JobService:
    return JobService(get_job_store())


@lru_cache
def get_routing_service() -> RoutingService:
    return RoutingService(ROUTES)


@lru_cache
def get_cpu_executor() -> InferenceExecutor:
    return InferenceExecutor(device="cpu", max_workers=8)


@lru_cache
def get_gpu_executor() -> InferenceExecutor:
    return InferenceExecutor(device="gpu", max_workers=2)


@lru_cache
def get_execution_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        executors={"cpu": get_cpu_executor(), "gpu": get_gpu_executor()},
        policy=EXECUTION_POLICY,
        default=DEFAULT_EXECUTOR,
    )


def get_prediction_service() -> PredictionService:
    return PredictionService(
        registry=get_registry(),
        executor=None,
        routing_service=get_routing_service(),
        execution_policy=get_execution_policy(),
        job_service=get_job_service(),
    )


@lru_cache
def get_async_service() -> AsyncInferenceService:
    return AsyncInferenceService(get_prediction_service())
