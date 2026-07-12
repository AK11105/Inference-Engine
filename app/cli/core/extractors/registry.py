"""ExtractorRegistry — priority-ordered collection of BaseExtractor instances.

Usage:
    registry = ExtractorRegistry()
    registry.register(OnnxExtractor())
    registry.register(GenericExtractor())

    extractor = registry.resolve(path, raw_facts)
    if extractor:
        raw_facts = extractor.extract(path, raw_facts)
"""
from __future__ import annotations

from .base import BaseExtractor


class ExtractorRegistry:
    """Registry that resolves the best-matching extractor for a given artifact.

    Extractors are tried in descending priority order. The first whose
    can_handle() returns True wins.
    """

    def __init__(self) -> None:
        self._extractors: dict[str, BaseExtractor] = {}

    def register(self, extractor: BaseExtractor) -> None:
        """Register an extractor. Replaces any existing extractor with the same name."""
        self._extractors[extractor.name] = extractor

    def unregister(self, name: str) -> None:
        """Remove an extractor by name. No-op if not found."""
        self._extractors.pop(name, None)

    def resolve(self, path: str, raw_facts: dict) -> BaseExtractor | None:
        """Return the highest-priority extractor that can handle the artifact.

        Returns None if no extractor matches.
        """
        for ext in self._sorted():
            if ext.can_handle(path, raw_facts):
                return ext
        return None

    def list(self) -> list[BaseExtractor]:
        """Return all registered extractors sorted by priority (descending)."""
        return self._sorted()

    def _sorted(self) -> list[BaseExtractor]:
        """Internal: return extractors sorted by priority descending."""
        return sorted(self._extractors.values(), key=lambda e: e.priority, reverse=True)
