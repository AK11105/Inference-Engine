from fastapi import FastAPI, Request
import uuid

from app.adapters.http.routes import router as api_router
from app.core.logging import setup_logging

from app.adapters.http.middleware.auth import AuthMiddleware
from app.adapters.http.middleware.rate_limit import RateLimitMiddleware
from app.adapters.http.middleware.payload_guard import PayloadGuardMiddleware

def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Inference Engine",
        version="0.1.0",
    )
    
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    
    app.add_middleware(PayloadGuardMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(RateLimitMiddleware)
    
    app.include_router(api_router)
    
    return app

app = create_app()