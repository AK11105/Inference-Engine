from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Optional
import threading

class ExecutionTimeoutError(Exception):
    pass 

class ExecutorSaturatedError(Exception):
    pass

class InferenceExecutor:
    """
    Centralized execution engine for ML inference
    
    - Isolates ML compute from HTTP concurrency
    - Enforces concurrency limits
    - Enforces per-request timeouts
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        default_timeout_s: Optional[float] = None,
    ):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._default_timeout_s = default_timeout_s
        self._lock = threading.Lock()
        
    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        """
        Submit a callable for execution and block until completion
        (blocking here is intentional); HTTP layer stays async-free
        """
        try:
            future = self._executor.submit(fn, *args)
        except RuntimeError as e:
            raise ExecutorSaturatedError("Executor Unavailable") from e
        
        timeout = timeout_s if timeout_s is not None else self._default_timeout_s
        
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout as e:
            future.cancel()
            raise ExecutionTimeoutError("Inference Execution Timed Out") from e