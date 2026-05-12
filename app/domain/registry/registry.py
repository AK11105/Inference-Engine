import importlib.util
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Tuple, List, Callable, Optional

from app.domain.pipelines import InferencePipeline
from app.domain.definitions import echo_v1, echo_v2

logger = logging.getLogger(__name__)


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
        except Exception as exc:
            logger.warning("Failed to load definition %s: %s", definition_file, exc)

    return found


class ModelRegistry:
    """
    Resolves (model_name, version) -> InferencePipeline
    with thread-safe lazy loading, in-memory caching, and LRU eviction.

    Definitions are sourced from two places (merged, discovered wins on conflict):
      1. Built-in definitions (echo_v1, echo_v2)
      2. Auto-discovered definitions under `models_dir` (default: "models/")

    Phase 4 additions:
      - max_loaded: evict least-recently-used pipelines when the cache exceeds
        this limit.  None means unlimited (original behaviour).
      - reload(name, version): hot-reload a single pipeline without restart.
    """

    def __init__(
        self,
        models_dir: str | Path = "models",
        max_loaded: Optional[int] = None,
    ):
        self._max_loaded = max_loaded
        # OrderedDict used as an LRU cache: most-recently-used at the end.
        self._pipelines: OrderedDict[Tuple[str, str], InferencePipeline] = OrderedDict()
        self._definitions: Dict[Tuple[str, str], Callable] = {
            (echo_v1.MODEL_NAME, echo_v1.MODEL_VERSION): echo_v1.build_pipeline,
            (echo_v2.MODEL_NAME, echo_v2.MODEL_VERSION): echo_v2.build_pipeline,
        }
        # Discovered definitions override built-ins on key collision
        self._definitions.update(_discover_definitions(Path(models_dir)))

        self._locks: Dict[Tuple[str, str], threading.Lock] = {
            key: threading.Lock() for key in self._definitions
        }
        # Global lock guards LRU eviction (OrderedDict mutations)
        self._lru_lock = threading.Lock()
        # Keys that failed to load during warm_up — excluded from is_ready check
        self._failed_keys: set = set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evict_if_needed(self) -> None:
        """Evict the LRU pipeline if the cache is over the limit. Caller holds _lru_lock."""
        if self._max_loaded is None:
            return
        while len(self._pipelines) > self._max_loaded:
            evicted_key, _ = self._pipelines.popitem(last=False)  # FIFO = LRU end

    def _touch(self, key: Tuple[str, str]) -> None:
        """Mark key as most-recently-used. Caller holds _lru_lock."""
        if key in self._pipelines:
            self._pipelines.move_to_end(key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, model_name: str, version: str) -> InferencePipeline:
        key = (model_name, version)
        if key not in self._definitions:
            raise ModelNotFoundError(
                f"Model '{model_name}' with version '{version}' not found."
            )

        with self._lru_lock:
            if key in self._pipelines:
                self._touch(key)
                return self._pipelines[key]

        # Not in cache — build under per-key lock (double-checked)
        with self._locks[key]:
            with self._lru_lock:
                if key in self._pipelines:
                    self._touch(key)
                    return self._pipelines[key]

            pipeline = self._definitions[key]()

            with self._lru_lock:
                self._pipelines[key] = pipeline
                self._touch(key)
                self._evict_if_needed()

        return pipeline

    def reload(self, model_name: str, version: str) -> InferencePipeline:
        """
        Hot-reload a single pipeline.

        Evicts the cached pipeline (if any) and rebuilds it from its definition.
        Thread-safe: in-flight requests using the old pipeline complete normally;
        subsequent requests get the new one.

        Raises ModelNotFoundError if the model/version is not registered.
        """
        key = (model_name, version)
        if key not in self._definitions:
            raise ModelNotFoundError(
                f"Model '{model_name}' with version '{version}' not found."
            )

        with self._locks[key]:
            # Drop from cache so the next get() rebuilds
            with self._lru_lock:
                self._pipelines.pop(key, None)
            # Build fresh
            pipeline = self._definitions[key]()
            with self._lru_lock:
                self._pipelines[key] = pipeline
                self._touch(key)
                self._evict_if_needed()

        return pipeline

    def warm_up(self) -> None:
        """Load all registered pipelines eagerly. Call at startup."""
        for key in self._definitions:
            t = time.time()
            try:
                self.get(key[0], key[1])
                logger.info(
                    "registry: loaded %s:%s in %.0fms",
                    key[0], key[1], (time.time() - t) * 1000,
                )
            except Exception as exc:
                logger.error("registry: failed to load %s:%s — %s", key[0], key[1], exc)
                self._failed_keys.add(key)

    def is_ready(self) -> bool:
        required = set(self._definitions) - self._failed_keys
        return all(key in self._pipelines for key in required)

    def list_models(self) -> List[Tuple[str, str]]:
        return list(self._definitions.keys())
