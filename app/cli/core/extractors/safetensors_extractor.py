"""SafetensorsExtractor — handles .safetensors files."""
from __future__ import annotations

from .base import BaseExtractor


class SafetensorsExtractor(BaseExtractor):
    """Handles safetensors format files (.safetensors)."""

    name = "safetensors"
    priority = 60

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("format") == "safetensors"

    def extract(self, path: str, raw_facts: dict) -> dict:
        import safetensors

        raw_facts["framework"] = "safetensors"
        with safetensors.safe_open(path, framework="pt") as f:
            keys = list(f.keys())
            raw_facts["tensor_keys"] = keys[:30]
            raw_facts["metadata"] = f.metadata() or {}
            raw_facts["tensor_shapes"] = {k: list(f.get_slice(k).get_shape()) for k in keys[:10]}

        if raw_facts["metadata"].get("format") == "pt":
            raw_facts["framework"] = "pytorch"

        return raw_facts
