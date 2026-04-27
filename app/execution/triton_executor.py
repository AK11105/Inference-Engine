"""
TritonExecutor — delegates inference to a Triton Inference Server via gRPC.

The pipeline's preprocessor and postprocessor still run locally; only
the model.predict() call is replaced by a Triton gRPC request.

This executor wraps the remote call in a thread pool so the FastAPI
event loop is never blocked.

Requires: tritonclient[grpc]
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

from app.execution.base import BaseExecutor
from app.execution.executor import ExecutionTimeoutError


class TritonExecutor(BaseExecutor):
    """
    Sends inference requests to a remote Triton Inference Server.

    The callable passed to submit() is expected to be a zero-arg lambda
    that calls the Triton gRPC client.  The executor manages the thread
    pool and timeout.
    """

    def __init__(self, url: str = "localhost:8001", max_workers: int = 8):
        try:
            import tritonclient.grpc  # noqa: F401 — validate availability
        except ImportError as e:
            raise RuntimeError(
                "tritonclient[grpc] is required for TritonExecutor"
            ) from e
        self._url = url
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        future = self._executor.submit(fn, *args)
        try:
            return future.result(timeout=timeout_s)
        except FuturesTimeout as e:
            raise ExecutionTimeoutError("Triton inference timed out") from e

    def submit_background(self, fn, *args) -> None:
        try:
            self._executor.submit(fn, *args)
        except RuntimeError:
            pass
