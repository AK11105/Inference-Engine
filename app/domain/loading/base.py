"""
ModelLoader interface — abstracts artifact retrieval from any storage backend.

A loader is responsible for fetching raw artifact bytes or a local path
so that a model's load() method can consume them.  The inference engine
core never imports storage SDKs directly.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class ModelLoader(ABC):
    """
    Fetch model artifacts from a storage backend.

    Implementations: LocalModelLoader, S3ModelLoader, GCSModelLoader, …
    """

    @abstractmethod
    def load(self, model_name: str, version: str) -> Path:
        """
        Return a local filesystem path to the artifact directory.

        Implementations may download to a temp dir and return that path.
        The caller must not delete the path while the model is in use.
        """
        raise NotImplementedError
