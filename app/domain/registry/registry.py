import threading
from typing import Dict, Tuple, List

from app.domain.pipelines import InferencePipeline
from app.domain.definitions import echo_v1, echo_v2


class ModelNotFoundError(Exception):
    pass


class ModelRegistry:
    """
    Resolves (model_name, version) -> InferencePipeline
    with thread-safe lazy loading and in-memory caching.
    """

    def __init__(self):
        self._pipelines: Dict[Tuple[str, str], InferencePipeline] = {}
        self._definitions = {
            (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
            (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline,
        }
        self._locks: Dict[Tuple[str, str], threading.Lock] = {
            key: threading.Lock() for key in self._definitions
        }

    def get(self, model_name: str, version: str) -> InferencePipeline:
        key = (model_name, version)
        if key not in self._definitions:
            raise ModelNotFoundError(
                f"Model '{model_name}' with version '{version}' not found."
            )

        # Fast path — already loaded
        if key in self._pipelines:
            return self._pipelines[key]

        # Slow path — load under per-key lock to prevent duplicate builds
        with self._locks[key]:
            if key not in self._pipelines:
                self._pipelines[key] = self._definitions[key]()
        return self._pipelines[key]

    def warm_up(self) -> None:
        """Load all registered pipelines eagerly. Call at startup."""
        for key in self._definitions:
            self.get(key[0], key[1])

    def is_ready(self) -> bool:
        """True only when all registered models are loaded."""
        return all(key in self._pipelines for key in self._definitions)

    def list_models(self) -> List[Tuple[str, str]]:
        """Return all available (model_name, version) pairs."""
        return list(self._definitions.keys())
