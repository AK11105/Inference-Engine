from fastapi import APIRouter, Request, HTTPException
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from app.security.permissions import require_scope
from app.core.metrics import REGISTRY

router = APIRouter()

@router.get("/metrics")
def metrics(http_request: Request):
    try:
        require_scope(http_request.state.identity, "admin")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)