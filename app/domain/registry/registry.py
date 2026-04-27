import importlib.util
import threading
from pathlib import Path
from typing import Dict, Tuple, List, Callable

from app.domain.pipelines import InferencePipeline
from app.domain.definitions import echo_v1, echo_v2


class ModelNotFoundError(Exception):
    pass


def _discover_definitions(models_dir: Path) -> Dict[Tuple[str, str], Callable]:
    """
    Scan <models_dir>/<model_name>/<version>/definition.py for build_pipeline().

    Each definition module must expose:
        MODEL_NAME: str
        MODEL_VERSION: str
        build_pipeline() -> InferencePipeline
    """
    found: Dict[Tuple[str, str], Callable] = {}
    if not models_dir.is_dir():
        return found

    for definition_file in sorted(models_dir.glob("*/*/definition.py")):
        spec = importlib.util.spec_from_file_location(
            f"_discovered.{definition_file.parent.parent.name}.{definition_file.parent.name}",
            definition_file,
        )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            key = (module.MODEL_NAME, module.MODEL_VERSION)
            found[key] = module.build_pipeline
        except Exception:
            pass  # malformed definition — skip silently

    return found


class ModelRegistry:
    """
    Resolves (model_name, version) -> InferencePipeline
    with thread-safe lazy loading and in-memory caching.

    Definitions are sourced from two places (merged, discovered wins on conflict):
      1. Built-in definitions (echo_v1, echo_v2)
      2. Auto-discovered definitions under `models_dir` (default: "models/")
    """

    def __init__(self, models_dir: str | Path = "models"):
        self._pipelines: Dict[Tuple[str, str], InferencePipeline] = {}
        self._definitions: Dict[Tuple[str, str], Callable] = {
            (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
            (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline,
        }
        # Discovered definitions override built-ins on key collision
        self._definitions.update(_discover_definitions(Path(models_dir)))

        self._locks: Dict[Tuple[str, str], threading.Lock] = {
            key: threading.Lock() for key in self._definitions
        }

    def get(self, model_name: str, version: str) -> InferencePipeline:
        key = (model_name, version)
        if key not in self._definitions:
            raise ModelNotFoundError(
                f"Model '{model_name}' with version '{version}' not found."
            )

        if key in self._pipelines:
            return self._pipelines[key]

        with self._locks[key]:
            if key not in self._pipelines:
                self._pipelines[key] = self._definitions[key]()
        return self._pipelines[key]

    def warm_up(self) -> None:
        """Load all registered pipelines eagerly. Call at startup."""
        for key in self._definitions:
            self.get(key[0], key[1])

    def is_ready(self) -> bool:
        return all(key in self._pipelines for key in self._definitions)

    def list_models(self) -> List[Tuple[str, str]]:
        return list(self._definitions.keys())
