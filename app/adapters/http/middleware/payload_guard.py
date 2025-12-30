from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MAX_BYTES = 1_000_000 #1MB

class PayloadGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT"}:
            body = await request.body()
            if len(body) > MAX_BYTES:
                return JSONResponse(
                    {"detail": "Payload too large"},
                    status_code=413
                )
        return await call_next(request)