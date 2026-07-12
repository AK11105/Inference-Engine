"""DirectoryExtractor — handles directory-based model artifacts (HF, TF saved models)."""
from __future__ import annotations

import json
import os

from .base import BaseExtractor


class DirectoryExtractor(BaseExtractor):
    """Handles directory artifacts (HuggingFace models, TF SavedModel, etc.)."""

    name = "directory"
    priority = 60

    def can_handle(self, path: str, raw_facts: dict) -> bool:
        return raw_facts.get("is_directory", False) or raw_facts.get("format") == "directory"

    def extract(self, path: str, raw_facts: dict) -> dict:
        files = os.listdir(path)
        raw_facts["directory_files"] = files
        raw_facts["framework"] = "unknown"

        cfg_path = os.path.join(path, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            raw_facts["hf_config"] = {
                "model_type": cfg.get("model_type"),
                "architectures": cfg.get("architectures"),
                "hidden_size": cfg.get("hidden_size"),
                "num_labels": cfg.get("num_labels"),
                "num_hidden_layers": cfg.get("num_hidden_layers"),
            }
            raw_facts["framework"] = "transformers"

        tok_path = os.path.join(path, "tokenizer_config.json")
        if os.path.exists(tok_path):
            with open(tok_path) as f:
                raw_facts["tokenizer_class"] = json.load(f).get("tokenizer_class")

        if "saved_model.pb" in files:
            raw_facts["format"] = "tf_savedmodel"
            raw_facts["framework"] = "tensorflow"

        if "adapter_config.json" in files:
            raw_facts["is_peft_adapter"] = True

        return raw_facts
