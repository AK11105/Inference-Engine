"""
Rate-limit middleware.

Selects Redis-backed or in-process limiter based on REDIS_URL env var.
Falls back silently to in-process when Redis is unavailable.
"""
import os

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security.rate_limit import make_rate_limiter

_redis_client = None

def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.environ.get("REDIS_URL", "").strip()
    if not redis_url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(redis_url, socket_connect_timeout=1)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


def _build_limits():
    rc = _get_redis_client()
    return {
        "/predict": make_rate_limiter(rate=10, per_seconds=1, name="predict", redis_client=rc),
        "/models": make_rate_limiter(rate=2, per_seconds=1, name="models", redis_client=rc),
        "/metrics": make_rate_limiter(rate=1, per_seconds=10, name="metrics", redis_client=rc),
    }


LIMITS = _build_limits()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        identity = getattr(request.state, "identity", None)
        if not identity:
            return await call_next(request)

        limiter = LIMITS.get(request.url.path)
        if limiter and not limiter.allow(identity.api_key):
            return JSONResponse(
                {"detail": "Rate Limit Exceeded"},
                status_code=429,
            )
        return await call_next(request)
