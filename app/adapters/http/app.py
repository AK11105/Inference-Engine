import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request

from app.adapters.http.routes import router as api_router
from app.core.logging import setup_logging, get_logger
from app.core.tracing import setup_tracing
from app.core import context
from app.adapters.http.middleware.auth import AuthMiddleware
from app.adapters.http.middleware.rate_limit import RateLimitMiddleware
from app.adapters.http.middleware.payload_guard import PayloadGuardMiddleware
import app.adapters.http.deps as _deps

logger = logging.getLogger(__name__)
_events = get_logger(__name__)
_COMPONENT = "Server"
_UNKNOWN_TENANT = "unknown"

_log_listener = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ startup

    # Initialise job store (async for Postgres).
    await _deps.init_job_store()

    # Fix 3: reap any jobs stuck in RUNNING from a previous crash.
    try:
        job_service = _deps.get_job_service()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        reaped = await job_service.reap_stuck(before=cutoff)
        if reaped:
            logger.warning("startup: reaped %d stuck job(s) from previous run", reaped)
    except Exception as exc:
        logger.warning("startup: reap_stuck failed: %s", exc)

    registry = _deps.get_registry()
    registry.warm_up()

    # Wire arq queue into AsyncInferenceService when Redis is available.
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings
            pool = await create_pool(RedisSettings.from_dsn(redis_url))
            from app.infra.queue.queue import ArqJobQueue
            _deps.get_async_service()._queue = ArqJobQueue(pool)
        except Exception as exc:
            logger.error("REDIS_URL is set but Redis is unreachable: %s", exc)
            raise RuntimeError(f"REDIS_URL is set but Redis is unreachable: {exc}") from exc

    _events.info(
        event="ServerStarted", component=_COMPONENT,
        version=app.version, env=os.environ.get("ENV", "development"),
    )

    yield

    # ----------------------------------------------------------------- shutdown
    logger.info("shutdown: draining executors")
    try:
        for getter in (_deps.get_cpu_executor, _deps.get_gpu_executor):
            try:
                executor = getter()
                executor._executor.shutdown(wait=True, cancel_futures=False)
            except Exception:
                pass
        _deps.get_cpu_executor.cache_clear()
        _deps.get_gpu_executor.cache_clear()
        _deps.get_execution_policy.cache_clear()
        _deps.get_prediction_service.cache_clear()
        _deps.get_async_service.cache_clear()
        _deps.get_job_service.cache_clear()
        _deps.get_registry.cache_clear()
        _deps.get_routing_service.cache_clear()
        # Reset the module-level job store so the next startup re-initialises it.
        _deps._job_store = None
    except Exception as exc:
        logger.warning("shutdown: executor drain error: %s", exc)

    logger.info("shutdown: complete")
    _events.info(event="ServerStopped", component=_COMPONENT)

    if _log_listener is not None:
        _log_listener.stop()


def create_app() -> FastAPI:
    global _log_listener
    _log_listener = setup_logging()

    if os.environ.get("ENV") == "production" and not os.environ.get("API_KEYS", "").strip():
        raise RuntimeError(
            "API_KEYS must be set in production. "
            "Set ENV=development to use hardcoded dev keys."
        )

    app = FastAPI(
        title="Inference Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    setup_tracing(app)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        context.set_correlation_context(request_id=request_id)
        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            _events.info(
                event="HTTPRequestCompleted",
                component="AccessLog",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                latency_ms=(time.time() - start) * 1000,
                client_ip=request.client.host if request.client else None,
                tenant_id=getattr(request.state, "tenant_id", _UNKNOWN_TENANT),
            )

    app.add_middleware(PayloadGuardMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    app.include_router(api_router)

    return app


app = create_app()
