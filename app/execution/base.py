"""
BaseExecutor — plugin interface for inference execution backends.

Implementations:
  - InferenceExecutor   (ThreadPoolExecutor, default)
  - OnnxExecutor        (ONNX Runtime)
  - TritonExecutor      (Triton Inference Server gRPC client)
  - TorchCompileExecutor (torch.compile wrapper)
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseExecutor(ABC):
    """
    Pluggable execution backend.

    All executors must implement submit() and submit_background().
    submit_batch() has a default implementation that delegates to submit().
    """

    @abstractmethod
    def submit(self, fn, *args, timeout_s: Optional[float] = None) -> Any:
        """Run fn(*args) synchronously, respecting timeout_s if given."""
        raise NotImplementedError

    def submit_batch(self, fn, timeout_s: Optional[float] = None) -> Any:
        """Execute a zero-arg batch callable. Override for optimised batching."""
        return self.submit(fn, timeout_s=timeout_s)

    @abstractmethod
    def submit_background(self, fn, *args) -> None:
        """Fire-and-forget execution for async jobs."""
        raise NotImplementedError
