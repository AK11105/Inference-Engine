import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional

from app.core.metrics import EXECUTOR_INFLIGHT, EXECUTOR_TIMEOUTS


class ExecutionTimeoutError(Exception):
    pass


class ExecutorSaturatedError(Exception):
    pass


class InferenceExecutor:
    def __init__(
        self,
        device: str,
        max_workers: int = 4,
        default_timeout_s: Optional[float] = None,
    ):
        self.device = device 
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._default_timeout_s = default_timeout_s

    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        start = time.time()
        EXECUTOR_INFLIGHT.labels(self.device).inc()

        try:
            future = self._executor.submit(fn, *args)
            timeout = timeout_s if timeout_s is not None else self._default_timeout_s
            return future.result(timeout=timeout)

        except FuturesTimeout as e:
            EXECUTOR_TIMEOUTS.labels(self.device).inc()
            raise ExecutionTimeoutError("Inference execution timed out") from e

        finally:
            EXECUTOR_INFLIGHT.labels(self.device).dec()
    
    def submit_batch(self, fn, timeout_s: Optional[float] = None):
        """
        Execute batch inference (zero-arg callable).
        Batch semantics belong to the pipeline, not the executor.
        """
        return self.submit(fn, timeout_s=timeout_s)

    
    def submit_background(self, fn, *args) -> None:
        """
        Fire and Forget execution
        Used for async inference jobs
        """
        try:
            self._executor.submit(fn, *args)
        except RuntimeError:
            pass #executor shutting down or unavailable