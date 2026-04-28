"""
Admin routes — hot-reload and memory management.

POST /admin/models/{name}/{version}/reload
    Evicts the cached pipeline and rebuilds it from its definition.
    Requires admin scope.

GET /admin/models/memory
    Returns the current loaded-pipeline count and max_loaded limit.
    Requires admin scope.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.http.deps import get_registry
from app.domain.registry.registry import ModelRegistry, ModelNotFoundError
from app.security.permissions import require_scope

router = APIRouter(prefix="/admin")


@router.post("/models/{name}/{version}/reload")
def reload_model(
    name: str,
    version: str,
    http_request: Request,
    registry: ModelRegistry = Depends(get_registry),
):
    try:
        require_scope(http_request.state.identity, "admin")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    try:
        registry.reload(name, version)
    except ModelNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"reloaded": True, "model": name, "version": version}


@router.get("/models/memory")
def memory_status(
    http_request: Request,
    registry: ModelRegistry = Depends(get_registry),
):
    try:
        require_scope(http_request.state.identity, "admin")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {
        "loaded": len(registry._pipelines),
        "max_loaded": registry._max_loaded,
        "models": [
            {"name": n, "version": v}
            for (n, v) in registry._pipelines.keys()
        ],
    }
