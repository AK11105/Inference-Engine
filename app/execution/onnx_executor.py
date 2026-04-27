"""
OnnxExecutor — runs inference via ONNX Runtime in a thread pool.

The pipeline's model.predict() is still called; this executor simply
ensures the thread pool is sized for CPU-bound ONNX workloads and
that onnxruntime is available at construction time.

Requires: onnxruntime
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

from app.execution.base import BaseExecutor
from app.execution.executor import ExecutionTimeoutError


class OnnxExecutor(BaseExecutor):
    """
    Thread-pool executor optimised for ONNX Runtime workloads.

    ONNX Runtime releases the GIL during inference, so a thread pool
    gives real parallelism for CPU-bound models.
    """

    def __init__(self, max_workers: int = 4):
        try:
            import onnxruntime  # noqa: F401 — validate availability at startup
        except ImportError as e:
            raise RuntimeError("onnxruntime is required for OnnxExecutor") from e
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        future = self._executor.submit(fn, *args)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout as e:
            raise ExecutionTimeoutError("ONNX inference timed out") from e

    def submit_background(self, fn, *args) -> None:
        try:
            self._executor.submit(fn, *args)
        except RuntimeError:
            pass
