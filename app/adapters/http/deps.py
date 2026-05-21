"""
Dependency providers for FastAPI routes.
"""
import logging
import os
from functools import lru_cache

from app.domain.registry import ModelRegistry
from app.services import PredictionService, AsyncInferenceService
from app.execution import InferenceExecutor
from app.services.routing_service import RoutingService
from app.config.routing import ROUTES
from app.execution.execution_policy import ExecutionPolicy
from app.config.execution import EXECUTION_POLICY, DEFAULT_EXECUTOR
from app.services.job_service import JobService
from app.domain.jobs.job_store import JobStore


_log = logging.getLogger(__name__)

# Populated during lifespan startup (async init required for Postgres).
_job_store: JobStore | None = None


async def init_job_store() -> JobStore:
    """Initialise and cache the job store. Called once from lifespan startup."""
    global _job_store
    if _job_store is not None:
        return _job_store

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        from app.infra.jobs.postgres_job_store import PostgresJobStore
        try:
            _job_store = await PostgresJobStore.create_pool(dsn=db_url)
        except Exception as exc:
            _log.error("DATABASE_URL is set but Postgres is unreachable: %s", exc)
            raise RuntimeError(f"DATABASE_URL is set but Postgres is unreachable: {exc}") from exc
        return _job_store

    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    _job_store = SQLiteJobStore()
    return _job_store


def get_job_store() -> JobStore:
    """FastAPI dependency — store must already be initialised by lifespan."""
    if _job_store is None:
        # Fallback for tests that don't go through lifespan.
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        return SQLiteJobStore()
    return _job_store


@lru_cache
def get_registry() -> ModelRegistry:
    return ModelRegistry()


@lru_cache
def get_job_service() -> JobService:
    return JobService(get_job_store())


@lru_cache
def get_routing_service() -> RoutingService:
    return RoutingService(ROUTES)


@lru_cache
def get_cpu_executor() -> InferenceExecutor:
    workers = int(os.environ.get("CPU_EXECUTOR_WORKERS", "8"))
    return InferenceExecutor(device="cpu", max_workers=workers)


@lru_cache
def get_gpu_executor() -> InferenceExecutor:
    workers = int(os.environ.get("GPU_EXECUTOR_WORKERS", "2"))
    return InferenceExecutor(device="gpu", max_workers=workers)


@lru_cache
def get_execution_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        executors={"cpu": get_cpu_executor(), "gpu": get_gpu_executor()},
        policy=EXECUTION_POLICY,
        default=DEFAULT_EXECUTOR,
    )


@lru_cache
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
    return AsyncInferenceService(
        prediction_service=get_prediction_service(),
        job_queue=None,  # populated at startup via lifespan if REDIS_URL is set
    )
