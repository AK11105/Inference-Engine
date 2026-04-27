"""
LocalModelLoader — serves artifacts from a local directory tree.

Expected layout:
    <root>/<model_name>/<version>/   (any files the model needs)

This is the default loader used when no remote storage is configured.
"""
from pathlib import Path

from app.domain.loading.base import ModelLoader


class LocalModelLoader(ModelLoader):
    def __init__(self, root: str | Path = "model_artifacts"):
        self._root = Path(root)

    def load(self, model_name: str, version: str) -> Path:
        path = self._root / model_name / version
        if not path.exists():
            raise FileNotFoundError(
                f"No artifact directory found at '{path}' "
                f"for model '{model_name}:{version}'"
            )
        return path
