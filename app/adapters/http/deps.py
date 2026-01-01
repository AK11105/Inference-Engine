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

_job_store = SQLiteJobStore()
_job_service = JobService(_job_store)

@lru_cache
def get_registry() -> ModelRegistry:
    # One Registry per process
    return ModelRegistry()

@lru_cache
def get_executor() -> InferenceExecutor:
    return InferenceExecutor(max_workers=4, default_timeout_s=10.0)

def get_prediction_service() -> PredictionService:
    registry = get_registry()
    executor = None
    routing_service=get_routing_service()
    execution_policy = get_execution_policy()
    job_service = get_job_service()
    return PredictionService(registry, executor, routing_service, execution_policy, job_service)

@lru_cache
def get_async_service() -> AsyncInferenceService:
    return AsyncInferenceService(get_prediction_service())

@lru_cache
def get_routing_service() -> RoutingService:
    return RoutingService(ROUTES)

@lru_cache
def get_cpu_executor():
    return InferenceExecutor(device="cpu", max_workers=8)

@lru_cache
def get_gpu_executor():
    return InferenceExecutor(device="gpu", max_workers=2)

@lru_cache
def get_execution_policy():
    executors = {
        "cpu": get_cpu_executor(),
        "gpu": get_gpu_executor(),
    }
    return ExecutionPolicy(
        executors=executors,
        policy=EXECUTION_POLICY,
        default=DEFAULT_EXECUTOR,
    )
    
def get_job_service() -> JobService:
    return _job_service