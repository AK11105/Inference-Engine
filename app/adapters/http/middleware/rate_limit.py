from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security.rate_limit import RateLimiter

LIMITS = {
    "/predict": RateLimiter(rate=10, per_seconds=1),
    "/models": RateLimiter(rate=2, per_seconds=1),
    "/metrics": RateLimiter(rate=1, per_seconds=10),
}

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        identity = getattr(request.state, "identity", None)
        if not identity:
            return await call_next(request)
        
        limiter = LIMITS.get(request.url.path)
        if limiter and not limiter.allow(identity.api_key):
            return JSONResponse(
                {"detail": "Rate Limit Exceeded"},
                status_code=429
            )
        return await call_next(request)