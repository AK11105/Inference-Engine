from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.security.auth import authenticate

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Public endpoints
        if request.url.path in {"/health"}:
            return await call_next(request)
        
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return JSONResponse({"detail": "Missing API Key"}, status_code=401)
    
        identity = authenticate(api_key)
        if not identity:
            return JSONResponse({"detail": "Invalid API Key"}, status_code=401)
        
        request.state.identity = identity
        request.state.tenant_id = identity.tenant_id
        return await call_next(request)
        