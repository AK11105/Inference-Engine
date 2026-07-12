"""Extractors package — plugin-based format discovery for artifact inspection.

Usage:
    from app.cli.core.extractors import default_registry

    registry = default_registry()
    extractor = registry.resolve(path, raw_facts)
    raw_facts = extractor.extract(path, raw_facts)
"""
from .base import BaseExtractor
from .registry import ExtractorRegistry
from .builtin import (
    PickleExtractor,
    TorchExtractor,
    OnnxExtractor,
    SafetensorsExtractor,
    DirectoryExtractor,
    GenericExtractor,
)


def default_registry() -> ExtractorRegistry:
    """Create a new ExtractorRegistry pre-loaded with all built-in extractors.

    Returns a fresh instance each call so callers can customize without
    polluting a shared global.
    """
    reg = ExtractorRegistry()
    reg.register(PickleExtractor())
    reg.register(TorchExtractor())
    reg.register(OnnxExtractor())
    reg.register(SafetensorsExtractor())
    reg.register(DirectoryExtractor())
    reg.register(GenericExtractor())
    return reg


__all__ = [
    "BaseExtractor",
    "ExtractorRegistry",
    "default_registry",
    "PickleExtractor",
    "TorchExtractor",
    "OnnxExtractor",
    "SafetensorsExtractor",
    "DirectoryExtractor",
    "GenericExtractor",
]
