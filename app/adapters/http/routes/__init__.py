from fastapi import APIRouter

from .health import router as health_router
from .predict import router as predict_router
from .models import router as models_router

router = APIRouter()

router.include_router(predict_router)
router.include_router(health_router)
router.include_router(models_router)

