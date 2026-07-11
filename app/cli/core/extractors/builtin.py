"""Built-in extractors — re-exports from individual modules.

Import all built-in extractors from here:
    from app.cli.core.extractors.builtin import PickleExtractor, OnnxExtractor, ...
"""
from .pickle_extractor import PickleExtractor
from .torch_extractor import TorchExtractor
from .onnx_extractor import OnnxExtractor
from .safetensors_extractor import SafetensorsExtractor
from .directory_extractor import DirectoryExtractor
from .generic_extractor import GenericExtractor

__all__ = [
    "PickleExtractor",
    "TorchExtractor",
    "OnnxExtractor",
    "SafetensorsExtractor",
    "DirectoryExtractor",
    "GenericExtractor",
]
