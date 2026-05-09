"""
arq worker definition.

Run the worker:
    arq app.infra.queue.worker.WorkerSettings
"""
import os
from typing import Any


async def run_inference(ctx: dict, job_id: str, model: str, version: str, payload: Any) -> None:
    from uuid import UUID
    job_service = ctx["job_service"]
    registry = ctx["registry"]

    uid = UUID(job_id)
    await job_service.mark_running(uid)
    try:
        pipeline = registry.get(model, version)
        result = pipeline.run(payload)
        await job_service.mark_succeeded(uid, result)
    except Exception as exc:
        await job_service.mark_failed(
            uid,
            error_types=type(exc).__name__,
            error_message=str(exc),
        )
        raise


async def run_batch_inference(
    ctx: dict, job_id: str, model: str, version: str, payloads: list
) -> None:
    from uuid import UUID
    job_service = ctx["job_service"]
    registry = ctx["registry"]

    uid = UUID(job_id)
    await job_service.mark_running(uid)
    try:
        pipeline = registry.get(model, version)
        result = pipeline.run_batch(payloads)
        await job_service.mark_succeeded(uid, result)
    except Exception as exc:
        await job_service.mark_failed(
            uid,
            error_types=type(exc).__name__,
            error_message=str(exc),
        )
        raise


async def startup(ctx: dict) -> None:
    from app.domain.registry.registry import ModelRegistry
    from app.services.job_service import JobService

    registry = ModelRegistry()
    registry.warm_up()
    ctx["registry"] = registry

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        from app.infra.jobs.postgres_job_store import PostgresJobStore
        store = await PostgresJobStore.create_pool(dsn=db_url)
    else:
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        store = SQLiteJobStore()

    ctx["job_service"] = JobService(store)


async def shutdown(ctx: dict) -> None:
    pass


from arq.connections import RedisSettings
from arq import cron


async def reap_stuck_jobs(ctx: dict) -> None:
    from datetime import datetime, timezone, timedelta
    job_service = ctx["job_service"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    count = await job_service.reap_stuck(before=cutoff)
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
