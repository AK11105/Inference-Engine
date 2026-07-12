"""BaseExtractor — abstract interface for artifact format extractors.

Every extractor must subclass BaseExtractor and implement:
- can_handle(path, raw_facts) -> bool
- extract(path, raw_facts) -> dict

The `priority` attribute controls evaluation order in the registry.
Higher priority = evaluated first. GenericExtractor should always be 0.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseExtractor(ABC):
    """Abstract base class for artifact metadata extractors.

    Attributes:
        name: Human-readable identifier for this extractor.
        priority: Integer priority (higher = tried first by the registry).
                  Default is 50. GenericExtractor uses 0.
    """

    name: str = "base"
    priority: int = 50

    @abstractmethod
    def can_handle(self, path: str, raw_facts: dict) -> bool:
        """Return True if this extractor can handle the given artifact.

        Args:
            path: Absolute path to the artifact file or directory.
            raw_facts: Dict with at least 'format', 'extension', 'is_directory'.
        """
        ...

    @abstractmethod
    def extract(self, path: str, raw_facts: dict) -> dict:
        """Extract metadata from the artifact and return updated raw_facts.

        Args:
            path: Absolute path to the artifact.
            raw_facts: Mutable dict to populate with extracted metadata.

        Returns:
            The (mutated) raw_facts dict with extracted fields added.
        """
        ...
