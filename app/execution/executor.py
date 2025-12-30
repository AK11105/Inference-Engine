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
        max_workers: int = 4,
        default_timeout_s: Optional[float] = None,
    ):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._default_timeout_s = default_timeout_s

    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        start = time.time()
        EXECUTOR_INFLIGHT.inc()

        try:
            future = self._executor.submit(fn, *args)
            timeout = timeout_s if timeout_s is not None else self._default_timeout_s
            return future.result(timeout=timeout)

        except FuturesTimeout as e:
            EXECUTOR_TIMEOUTS.inc()
            raise ExecutionTimeoutError("Inference execution timed out") from e

        finally:
            EXECUTOR_INFLIGHT.dec()
    
    def submit_batch(self, fn, payloads, timeout_s=None):
        """
        Execute batch inference inside executor
        """
        return self.submit(fn, payloads, timeout_s=timeout_s)
    
    def submit_background(self, fn, *args) -> None:
        """
        Fire and Forget execution
        Used for async inference jobs
        """
        try:
            self._executor.submit(fn, *args)
        except RuntimeError:
            pass #executor shutting down or unavailable