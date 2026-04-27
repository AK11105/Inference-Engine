"""
BaseValidator — input validation hook for InferencePipeline.

Validators run after preprocessing and before model inference.
They raise ValidationError on invalid input; the pipeline propagates it.

Implementations can check shape, dtype, value range, schema, etc.
"""
from abc import ABC, abstractmethod
from typing import Any


class ValidationError(ValueError):
    """Raised when pipeline input fails validation."""


class BaseValidator(ABC):
    @abstractmethod
    def validate(self, model_input: Any) -> None:
        """
        Inspect model_input and raise ValidationError if it is invalid.
        Must not mutate the input.
        """
        raise NotImplementedError


class NoOpValidator(BaseValidator):
    """Default validator — accepts everything."""

    def validate(self, model_input: Any) -> None:
        pass
