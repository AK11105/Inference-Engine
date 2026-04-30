"""
arq worker definition.

arq tasks are plain async functions that receive a WorkerContext as their
first argument.  The context carries shared state (registry, job_service)
that is initialised once per worker process in `startup`.

Run the worker:
    arq app.infra.queue.worker.WorkerSettings
"""
import os
from typing import Any


async def run_inference(ctx: dict, job_id: str, model: str, version: str, payload: Any) -> None:
    """
    arq task: execute a single inference job.

    The job record already exists in the store (created by the API handler).
    This task transitions it through RUNNING → SUCCEEDED / FAILED.
    """
    from uuid import UUID
    job_service = ctx["job_service"]
    registry = ctx["registry"]

    uid = UUID(job_id)
    job_service.mark_running(uid)
    try:
        pipeline = registry.get(model, version)
        result = pipeline.run(payload)
        job_service.mark_succeeded(uid, result)
    except Exception as exc:
        job_service.mark_failed(
            uid,
            error_types=type(exc).__name__,
            error_message=str(exc),
        )
        raise


async def run_batch_inference(
    ctx: dict, job_id: str, model: str, version: str, payloads: list
) -> None:
    """arq task: execute a batch inference job."""
    from uuid import UUID
    job_service = ctx["job_service"]
    registry = ctx["registry"]

    uid = UUID(job_id)
    job_service.mark_running(uid)
    try:
        pipeline = registry.get(model, version)
        result = pipeline.run_batch(payloads)
        job_service.mark_succeeded(uid, result)
    except Exception as exc:
        job_service.mark_failed(
            uid,
            error_types=type(exc).__name__,
            error_message=str(exc),
        )
        raise


async def startup(ctx: dict) -> None:
    """Initialise shared resources once per worker process."""
    from app.domain.registry.registry import ModelRegistry
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    from app.services.job_service import JobService

    registry = ModelRegistry()
    registry.warm_up()
    ctx["registry"] = registry

    # Use Postgres if DATABASE_URL is set, otherwise SQLite.
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        from app.infra.jobs.postgres_job_store import PostgresJobStore
        store = PostgresJobStore(dsn=db_url)
    else:
        store = SQLiteJobStore()

    ctx["job_service"] = JobService(store)


async def shutdown(ctx: dict) -> None:
    pass


from arq.connections import RedisSettings
from arq import cron


async def reap_stuck_jobs(ctx: dict) -> None:
    """Mark RUNNING jobs older than 10 minutes as FAILED."""
    from datetime import datetime, timezone, timedelta
    job_service = ctx["job_service"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    count = job_service.reap_stuck(before=cutoff)
    if count:
        import logging
        logging.getLogger(__name__).warning("reaped %d stuck job(s)", count)


class WorkerSettings:
    functions = [run_inference, run_batch_inference]
    cron_jobs = [cron(reap_stuck_jobs, minute={0, 10, 20, 30, 40, 50})]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )
    max_jobs = 10
    job_timeout = 300
