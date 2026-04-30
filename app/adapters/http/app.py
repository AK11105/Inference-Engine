import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from app.adapters.http.routes import router as api_router
from app.core.logging import setup_logging
from app.core.tracing import setup_tracing
from app.adapters.http.middleware.auth import AuthMiddleware
from app.adapters.http.middleware.rate_limit import RateLimitMiddleware
from app.adapters.http.middleware.payload_guard import PayloadGuardMiddleware
import app.adapters.http.deps as _deps

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ startup
    registry = _deps.get_registry()
    registry.warm_up()

    # Wire arq queue into AsyncInferenceService when Redis is available.
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if redis_url:
        try:
            from app.infra.queue.queue import create_queue
            queue = await create_queue(redis_url)
            if queue is not None:
                _deps.get_async_service()._queue = queue
        except Exception:
            pass  # arq not installed or Redis unreachable — fall back silently

    yield

    # ----------------------------------------------------------------- shutdown
    # Graceful shutdown: drain in-flight executor threads.
    # After draining, clear the lru_cache so a subsequent app startup
    # (e.g. in tests) gets fresh executor instances.
    logger.info("shutdown: draining executors")
    try:
        for getter in (_deps.get_cpu_executor, _deps.get_gpu_executor):
            try:
                executor = getter()
                executor._executor.shutdown(wait=True, cancel_futures=False)
            except Exception:
                pass
        # Clear cached singletons so the next startup gets fresh instances
        _deps.get_cpu_executor.cache_clear()
        _deps.get_gpu_executor.cache_clear()
        _deps.get_execution_policy.cache_clear()
        _deps.get_prediction_service.cache_clear()
        _deps.get_async_service.cache_clear()
        _deps.get_job_service.cache_clear()
        _deps.get_job_store.cache_clear()
        _deps.get_registry.cache_clear()
        _deps.get_routing_service.cache_clear()
    except Exception as exc:
        logger.warning("shutdown: executor drain error: %s", exc)

    logger.info("shutdown: complete")


def create_app() -> FastAPI:
    setup_logging()

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

    # Set up OpenTelemetry tracing (no-op when SDK not installed)
    setup_tracing(app)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.add_middleware(PayloadGuardMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    app.include_router(api_router)

    return app


app = create_app()
