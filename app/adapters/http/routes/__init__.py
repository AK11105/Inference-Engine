from fastapi import APIRouter

from .health import router as health_router
from .predict import router as predict_router
from .models import router as models_router
from .debug import router as debug_router
from .metrics import router as metrics_router
from .ready import router as ready_router
from .predict_batch import router as predict_batch_router
from .predict_async import router as predict_async_router
from .predict_async_batch import router as predict_async_batch_router
from .jobs import router as job_router

router = APIRouter()

router.include_router(predict_router)
router.include_router(health_router)
router.include_router(models_router)
router.include_router(metrics_router)
router.include_router(ready_router)
router.include_router(debug_router)
router.include_router(predict_batch_router)
router.include_router(predict_async_router)
router.include_router(predict_async_batch_router)
router.include_router(job_router)

