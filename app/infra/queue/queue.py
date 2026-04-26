"""
arq job queue client.

Provides a thin async wrapper around arq's ArqRedis for enqueuing inference
tasks.  Falls back to the synchronous ThreadPoolExecutor path when Redis is
unavailable (dev / test without Redis).
"""
import os
from typing import Any, Optional
from uuid import UUID


class ArqJobQueue:
    """
    Enqueues inference tasks onto the arq Redis queue.

    The arq worker (app.infra.queue.worker) picks them up and executes them.
    """

    def __init__(self, redis_pool):
        self._pool = redis_pool

    async def enqueue_inference(
        self,
        job_id: UUID,
        model: str,
        version: str,
        payload: Any,
    ) -> None:
        from app.infra.queue.worker import run_inference
        await self._pool.enqueue_job(
            "run_inference",
            str(job_id),
            model,
            version,
            payload,
        )

    async def enqueue_batch_inference(
        self,
        job_id: UUID,
        model: str,
        version: str,
        payloads: list,
    ) -> None:
        await self._pool.enqueue_job(
            "run_batch_inference",
            str(job_id),
            model,
            version,
            payloads,
        )


async def create_queue(redis_url: Optional[str] = None) -> Optional[ArqJobQueue]:
    """
    Create an ArqJobQueue connected to Redis.
    Returns None if Redis is unavailable (graceful degradation).
    """
    url = redis_url or os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        pool = await create_pool(RedisSettings.from_dsn(url))
        return ArqJobQueue(pool)
    except Exception:
        return None
