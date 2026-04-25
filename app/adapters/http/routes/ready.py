from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.adapters.http.deps import get_registry
from app.domain.registry import ModelRegistry

router = APIRouter()


@router.get("/ready")
def ready(registry: ModelRegistry = Depends(get_registry)):
    if registry.is_ready():
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "loading"})
