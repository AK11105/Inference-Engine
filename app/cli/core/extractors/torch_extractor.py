"""TorchExtractor — handles .pt/.pth PyTorch state dict and model files."""
from __future__ import annotations

from .base import BaseExtractor


class TorchExtractor(BaseExtractor):
    """Handles PyTorch .pt/.pth files (state dicts and full models)."""

    name = "pytorch"
    priority = 60

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("format") == "pytorch"

    def extract(self, path: str, raw_facts: dict) -> dict:
        import torch

        data = torch.load(path, map_location="cpu", weights_only=True)
        raw_facts["framework"] = "pytorch"

        if isinstance(data, dict):
            raw_facts["load_format"] = "state_dict"
            keys = list(data.keys())
            raw_facts["state_dict_keys"] = keys[:30]
            raw_facts["param_count"] = sum(
                v.numel() for v in data.values() if hasattr(v, "numel")
            )
        else:
            raw_facts["load_format"] = "full_model"
            raw_facts["class_name"] = type(data).__name__
            raw_facts["layer_names"] = [name for name, _ in data.named_children()]

        return raw_facts
