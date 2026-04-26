"""
Dependency providers for FastAPI routes.

Phase 2 additions:
- get_job_store() selects Postgres when DATABASE_URL is set, SQLite otherwise.
- get_async_service() injects the arq queue when REDIS_URL is set.
"""
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


@lru_cache
def get_registry() -> ModelRegistry:
    return ModelRegistry()


@lru_cache
def get_job_store() -> JobStore:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        try:
            from app.infra.jobs.postgres_job_store import PostgresJobStore
            return PostgresJobStore(dsn=db_url)
        except Exception:
            pass  # psycopg2 not installed or DB unreachable → fall through
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
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
    # Queue is None when Redis is unavailable; service falls back to thread pool.
    return AsyncInferenceService(
        prediction_service=get_prediction_service(),
        job_queue=None,  # populated at startup via lifespan if REDIS_URL is set
    )
