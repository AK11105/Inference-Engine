from fastapi import APIRouter

from .health import router as health_router
from .predict import router as predict_router
from .models import router as models_router
from .debug import router as debug_router
from .metrics import router as metrics_router
from .ready import router as ready_router

router = APIRouter()

router.include_router(predict_router)
router.include_router(health_router)
router.include_router(models_router)
router.include_router(metrics_router)
router.include_router(ready_router)
router.include_router(debug_router)

