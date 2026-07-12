from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# FieldValue — provenance wrapper for interpreted metadata fields (issue #56)
# ---------------------------------------------------------------------------

_SOURCE_PRIORITY: dict[str, int] = {
    "default": 0,
    "llm": 1,
    "filesystem": 2,
    "extractor": 3,
    "user": 4,
}


@dataclass(eq=False)
class FieldValue:
    """Wraps an interpreted metadata value with its provenance (source + confidence).

    Supports equality comparison and string formatting against the raw .value,
    so existing code like ``meta.framework == "sklearn"`` and f-string
    interpolation continue to work unchanged.
    """

    value: Any
    source: Literal["filesystem", "extractor", "llm", "user", "default"]
    confidence: Literal["high", "medium", "low"]

    # -- Equality delegates to .value for backward compat --------------------

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldValue):
            return self.value == other.value
        return self.value == other

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.value)

    # -- String representation delegates to .value ---------------------------

    def __str__(self) -> str:
        return str(self.value)

    def __format__(self, format_spec: str) -> str:
        return format(self.value, format_spec)

    def __repr__(self) -> str:
        return f"FieldValue(value={self.value!r}, source={self.source!r}, confidence={self.confidence!r})"

    # -- Bool: truthy if value is truthy -------------------------------------

    def __bool__(self) -> bool:
        return bool(self.value)

    # -- Explain mode --------------------------------------------------------

    def explain(self) -> str:
        """Return a human-readable provenance string."""
        return f"{self.value} (source: {self.source}, confidence: {self.confidence})"

    # -- Source hierarchy helpers ---------------------------------------------

    @staticmethod
    def source_priority(source: str) -> int:
        """Return numeric priority for a source. Higher = more authoritative."""
        return _SOURCE_PRIORITY.get(source, -1)

    @staticmethod
    def merge(a: "FieldValue | None", b: "FieldValue | None") -> "FieldValue | None":
        """Merge two FieldValues; the one with higher source priority wins.

        If one is None, returns the other.
        """
        if a is None:
            return b
        if b is None:
            return a
        if FieldValue.source_priority(a.source) >= FieldValue.source_priority(b.source):
            return a
        return b


# ---------------------------------------------------------------------------
# Subprocess inspection script
# ---------------------------------------------------------------------------
# Each extractor runs in an isolated subprocess so that importing heavy
# frameworks (torch, onnx, safetensors) doesn't pollute the CLI process.
# The script ALWAYS exits 0 and ALWAYS prints valid JSON — errors are
# captured in raw_facts["errors"] rather than raising.
# ---------------------------------------------------------------------------

_INSPECT_SCRIPT = r"""
from __future__ import annotations
import json, os, sys, struct

path = {path!r}

# ── Layer 0: filesystem facts (always succeeds) ────────────────────────────
raw = dict(
    artifact_path=path,
    artifact_size_mb=0.0,
    extension="",
    is_directory=False,
    errors=[],
)
try:
    raw["artifact_size_mb"] = round(os.path.getsize(path) / (1024 ** 2), 2)
    raw["extension"] = os.path.splitext(path)[1].lower()
    raw["is_directory"] = os.path.isdir(path)
except Exception as e:
    raw["errors"].append({{"layer": "filesystem", "error": str(e)}})

# ── Layer 1: format detection ──────────────────────────────────────────────
def _detect_format(p: str, ext: str) -> str:
    if os.path.isdir(p):
        return "directory"
    _EXT_MAP = {{
        ".pkl": "pickle", ".pickle": "pickle",
        ".joblib": "joblib",
        ".pt": "pytorch", ".pth": "pytorch",
        ".onnx": "onnx",
        ".safetensors": "safetensors",
    }}
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]
    # magic-byte fallback
    try:
        with open(p, "rb") as f:
            magic = f.read(8)
        if magic[:2] == b"\x80\x04" or magic[:2] == b"\x80\x05":
            return "pickle"
        if magic[:4] == b"PK\x03\x04":          # zip → likely torch
            return "pytorch"
        if magic[:4] == b"\x08\x00\x00\x00":    # protobuf → onnx
            return "onnx"
        if magic[:8] == b"<<< BEG":             # safetensors header marker
            return "safetensors"
    except Exception:
        pass
    return "unknown"

try:
    fmt = _detect_format(path, raw["extension"])
    raw["format"] = fmt
except Exception as e:
    raw["format"] = "unknown"
    raw["errors"].append({{"layer": "format", "error": str(e)}})
    fmt = "unknown"

# ── Layer 2: safe structural read (format-specific) ───────────────────────

def _extract_pickle(p: str, raw: dict) -> None:
    try:
        import joblib
        obj = joblib.load(p)
        raw["load_via"] = "joblib"
    except Exception:
        import pickle
        with open(p, "rb") as f:
            obj = pickle.load(f)
        raw["load_via"] = "pickle"

    raw["class_name"] = type(obj).__name__
    raw["module"] = type(obj).__module__ or ""
    try:
        raw["attributes"] = list(vars(obj).keys())
    except Exception:
        raw["attributes"] = []
    raw["has_predict"] = hasattr(obj, "predict")
    raw["has_predict_proba"] = hasattr(obj, "predict_proba")
    raw["has_steps"] = hasattr(obj, "steps")

    # ── framework detection ────────────────────────────────────────────────
    framework = "generic"
    module = raw["module"]

    try:
        from sentence_transformers import SentenceTransformer
        if isinstance(obj, SentenceTransformer):
            framework = "sentence_transformers"
    except Exception:
        pass

    if framework == "generic":
        try:
            from transformers import PreTrainedModel
            if isinstance(obj, PreTrainedModel):
                framework = "transformers"
        except Exception:
            pass

    if framework == "generic":
        try:
            import torch
            if isinstance(obj, torch.nn.Module):
                framework = "pytorch"
        except Exception:
            pass

    if framework == "generic":
        try:
            import xgboost as xgb
            if isinstance(obj, (xgb.XGBModel, xgb.Booster)):
                framework = "xgboost"
        except Exception:
            pass

    if framework == "generic":
        try:
            import lightgbm as lgb
            if isinstance(obj, (lgb.Booster, lgb.LGBMModel)):
                framework = "lightgbm"
        except Exception:
            pass

    if framework == "generic":
        try:
            from catboost import CatBoost
            if isinstance(obj, CatBoost):
                framework = "catboost"
        except Exception:
            pass

    if framework == "generic" and "sklearn" in module:
        framework = "sklearn"

    raw["framework"] = framework

    # ── Layer 3: deep attribute scan ──────────────────────────────────────
    try:
        if framework == "sklearn":
            if hasattr(obj, "steps"):
                raw["pipeline_steps"] = [type(s).__name__ for _, s in obj.steps]
            if hasattr(obj, "n_features_in_"):
                raw["n_features_in"] = int(obj.n_features_in_)
            if hasattr(obj, "classes_"):
                raw["classes"] = obj.classes_.tolist()
            elif hasattr(obj, "steps"):
                for _, step in obj.steps:
                    if hasattr(step, "classes_"):
                        raw["classes"] = step.classes_.tolist()
                        break

        elif framework == "pytorch":
            import torch
            layer_count = sum(1 for _ in obj.modules())
            raw["layer_count"] = layer_count
            children = list(obj.named_children())
            if children:
                raw["first_layer"] = type(children[0][1]).__name__
                raw["last_layer"] = type(children[-1][1]).__name__

        elif framework == "transformers":
            cfg = obj.config
            raw["model_type"] = getattr(cfg, "model_type", None)
            raw["hidden_size"] = getattr(cfg, "hidden_size", None)
            raw["num_labels"] = getattr(cfg, "num_labels", None)
            raw["tokenizer_class"] = getattr(cfg, "tokenizer_class", None)

        elif framework == "xgboost":
            import xgboost as xgb
            if isinstance(obj, xgb.XGBModel):
                raw["n_estimators"] = getattr(obj, "n_estimators", None)
                raw["objective"] = getattr(obj, "objective", None)
                if hasattr(obj, "n_features_in_"):
                    raw["n_features_in"] = int(obj.n_features_in_)
            elif isinstance(obj, xgb.Booster):
                raw["num_trees"] = obj.num_trees()

        elif framework == "lightgbm":
            import lightgbm as lgb
            if isinstance(obj, lgb.LGBMModel):
                raw["n_estimators"] = getattr(obj, "n_estimators", None)
                raw["objective"] = getattr(obj, "objective", None)
                if hasattr(obj, "n_features_in_"):
                    raw["n_features_in"] = int(obj.n_features_in_)
            elif isinstance(obj, lgb.Booster):
                raw["num_trees"] = obj.num_trees()

        elif framework == "catboost":
            from catboost import CatBoost
            raw["loss_function"] = obj.get_param("loss_function")
            fc = obj.get_param("feature_count") or obj.get_param("num_features")
            if fc is not None:
                raw["n_features_in"] = int(fc)

        elif framework == "sentence_transformers":
            raw["model_name"] = getattr(obj, "_model_card_text", None) or type(obj).__name__
            for m in obj.modules():
                if hasattr(m, "word_embedding_dimension"):
                    raw["embedding_dim"] = m.word_embedding_dimension
                    break

    except Exception as e:
        raw["errors"].append({{"layer": "deep", "error": str(e)}})


def _extract_pytorch(p: str, raw: dict) -> None:
    import torch
    # weights_only=True prevents arbitrary code execution
    data = torch.load(p, map_location="cpu", weights_only=True)
    raw["framework"] = "pytorch"
    if isinstance(data, dict):
        raw["load_format"] = "state_dict"
        keys = list(data.keys())
        raw["state_dict_keys"] = keys[:30]
        raw["param_count"] = sum(
            v.numel() for v in data.values() if hasattr(v, "numel")
        )
    else:
        raw["load_format"] = "full_model"
        raw["class_name"] = type(data).__name__
        raw["layer_names"] = [name for name, _ in data.named_children()]


def _extract_onnx(p: str, raw: dict) -> None:
    import onnx
    model = onnx.load(p)
    raw["framework"] = "onnx"
    raw["opset"] = model.opset_import[0].version if model.opset_import else None
    raw["op_types"] = list({{n.op_type for n in model.graph.node}})

    def _shape(tensor_type):
        if not tensor_type.HasField("shape"):
            return []
        return [
            d.dim_param if d.dim_param else d.dim_value
            for d in tensor_type.shape.dim
        ]

    raw["inputs"] = [
        {{"name": i.name, "shape": _shape(i.type.tensor_type), "dtype": i.type.tensor_type.elem_type}}
        for i in model.graph.input
    ]
    raw["outputs"] = [
        {{"name": o.name, "shape": _shape(o.type.tensor_type), "dtype": o.type.tensor_type.elem_type}}
        for o in model.graph.output
    ]


def _extract_safetensors(p: str, raw: dict) -> None:
    import safetensors
    raw["framework"] = "safetensors"
    with safetensors.safe_open(p, framework="pt") as f:
        keys = list(f.keys())
        raw["tensor_keys"] = keys[:30]
        raw["metadata"] = f.metadata() or {{}}
        raw["tensor_shapes"] = {{k: list(f.get_slice(k).get_shape()) for k in keys[:10]}}
    if raw["metadata"].get("format") == "pt":
        raw["framework"] = "pytorch"


def _extract_directory(p: str, raw: dict) -> None:
    files = os.listdir(p)
    raw["directory_files"] = files
    raw["framework"] = "unknown"

    cfg_path = os.path.join(p, "config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)
        raw["hf_config"] = {{
            "model_type": cfg.get("model_type"),
            "architectures": cfg.get("architectures"),
            "hidden_size": cfg.get("hidden_size"),
            "num_labels": cfg.get("num_labels"),
            "num_hidden_layers": cfg.get("num_hidden_layers"),
        }}
        raw["framework"] = "transformers"

    tok_path = os.path.join(p, "tokenizer_config.json")
    if os.path.exists(tok_path):
        with open(tok_path) as f:
            raw["tokenizer_class"] = json.load(f).get("tokenizer_class")

    if "saved_model.pb" in files:
        raw["format"] = "tf_savedmodel"
        raw["framework"] = "tensorflow"

    if "adapter_config.json" in files:
        raw["is_peft_adapter"] = True


# ── Registry-based dispatch (issue #57) ────────────────────────────────────
# Try importing the registry for plugin-based resolution. Falls back to the
# legacy _EXTRACTORS dict if the package isn't importable (e.g. standalone).
_EXTRACTORS = {{
    "pickle":       _extract_pickle,
    "joblib":       _extract_pickle,
    "pytorch":      _extract_pytorch,
    "onnx":         _extract_onnx,
    "safetensors":  _extract_safetensors,
    "directory":    _extract_directory,
}}

_used_registry = False
try:
    from app.cli.core.extractors import default_registry as _default_registry
    _registry = _default_registry()
    _extractor_obj = _registry.resolve(path, raw)
    if _extractor_obj is not None:
        try:
            raw = _extractor_obj.extract(path, raw)
            _used_registry = True
        except Exception as e:
            raw["errors"].append({{"layer": "extraction", "error": str(e)}})
            if "framework" not in raw:
                raw["framework"] = "unknown"
            _used_registry = True
except ImportError:
    pass

if not _used_registry:
    # Legacy fallback: use inline extractors if registry not available
    extractor = _EXTRACTORS.get(fmt)
    if extractor is not None:
        try:
            extractor(path, raw)
        except Exception as e:
            raw["errors"].append({{"layer": "extraction", "error": str(e)}})
            if "framework" not in raw:
                raw["framework"] = "unknown"
    else:
        # GenericExtractor: try joblib then pickle
        try:
            _extract_pickle(path, raw)
        except Exception as e:
            raw["errors"].append({{"layer": "extraction", "error": str(e)}})
            raw["framework"] = "unknown"

# ── Confidence ─────────────────────────────────────────────────────────────
def _confidence(r: dict) -> str:
    if len(r.get("errors", [])) > 1:
        return "low"
    if r.get("framework") in (None, "unknown"):
        return "low"
    skip = {{"errors", "artifact_path", "is_directory"}}
    filled = sum(1 for k, v in r.items() if k not in skip and v not in (None, "unknown", []))
    total = len(r) - len(skip)
    ratio = filled / total if total else 0
    if r.get("errors"):
        return "medium"
    return "high" if ratio > 0.5 else "medium"

raw["confidence"] = _confidence(raw)

# ── Build legacy-compatible ArtifactMetadata fields ───────────────────────
framework = raw.get("framework", "unknown")
class_name = raw.get("class_name", "unknown")
class_hierarchy = raw.get("pipeline_steps", [raw.get("class_name")] if raw.get("class_name") else [])
feature_count = raw.get("n_features_in")
class_labels = raw.get("classes")

# input/output hints
input_hint = "unknown"
output_hint = "unknown"
if framework == "sklearn":
    text_vecs = ("TfidfVectorizer", "CountVectorizer", "HashingVectorizer")
    if class_hierarchy and class_hierarchy[0] in text_vecs:
        input_hint = "raw text string"
    elif feature_count:
        input_hint = "array-like of shape (n, " + str(feature_count) + ")"
    else:
        input_hint = "array-like"
    if class_labels is not None:
        output_hint = "integer class label (classes: " + str(class_labels) + ")"
    else:
        output_hint = "float or array"
elif framework == "pytorch":
    input_hint = "torch.Tensor"
    output_hint = "torch.Tensor"
elif framework == "transformers":
    input_hint = "dict with input_ids, attention_mask (tokenized)"
    output_hint = "ModelOutput (logits or last_hidden_state)"
elif framework in ("xgboost", "lightgbm", "catboost"):
    input_hint = "numpy array or pandas DataFrame"
    output_hint = "numpy array of predictions"
elif framework == "sentence_transformers":
    input_hint = "string or list of strings"
    output_hint = "numpy array of shape (n, embedding_dim)"
elif framework == "onnx":
    input_hint = "numpy array matching ONNX input shape"
    output_hint = "numpy array matching ONNX output shape"

# extra dict (legacy field — keep for backward compat with existing tests/prompts)
extra = {{}}
for k in ("layer_count", "first_layer", "last_layer",
          "model_type", "hidden_size", "num_labels", "tokenizer_class",
          "n_estimators", "objective", "num_trees", "loss_function",
          "embedding_dim", "model_name",
          "state_dict_keys", "param_count", "layer_names", "load_format",
          "op_types", "opset", "tensor_keys", "metadata", "tensor_shapes",
          "hf_config", "directory_files", "is_peft_adapter"):
    if k in raw:
        extra[k] = raw[k]

# onnx inputs/outputs go into extra under legacy keys
if "inputs" in raw:
    extra["onnx_inputs"] = raw["inputs"]
if "outputs" in raw:
    extra["onnx_outputs"] = raw["outputs"]

if raw.get("errors"):
    extra["inspection_warning"] = "; ".join(e["error"] for e in raw["errors"])

print(json.dumps(dict(
    framework=framework,
    class_name=class_name,
    class_hierarchy=class_hierarchy,
    input_hint=input_hint,
    output_hint=output_hint,
    feature_count=feature_count,
    class_labels=class_labels,
    artifact_path=path,
    artifact_size_mb=raw["artifact_size_mb"],
    extra=extra,
    raw_facts=raw,
    confidence=raw["confidence"],
    inspection_errors=raw.get("errors", []),
)))
"""


@dataclass
class ArtifactMetadata:
    framework: FieldValue | None
    class_name: str
    class_hierarchy: list
    input_hint: FieldValue | None
    output_hint: FieldValue | None
    feature_count: int | None
    class_labels: list | None
    artifact_path: str
    artifact_size_mb: float
    extra: dict = field(default_factory=dict)
    # new fields (issue #15)
    raw_facts: dict = field(default_factory=dict)
    # issue #56: split confidence into two specific fields
    inspection_confidence: str = "low"
    interpretation_confidence: str = "low"
    inspection_errors: list = field(default_factory=list)
    # issue #56: promote load_format from extra to top-level FieldValue
    load_format: FieldValue | None = None


def inspect_artifact(path: str) -> ArtifactMetadata:
    """Inspect a model artifact in an isolated subprocess and return structured metadata."""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"Artifact not found: {abs_path}")

    script = _INSPECT_SCRIPT.format(path=abs_path)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise ValueError(f"Inspection failed:\n{result.stderr.strip()}")

    data = json.loads(result.stdout)

    # --- Issue #56: wrap interpreted fields in FieldValue with provenance ---
    raw_confidence = data.pop("confidence", "low")
    framework_val = data.pop("framework", "unknown")
    input_hint_val = data.pop("input_hint", "unknown")
    output_hint_val = data.pop("output_hint", "unknown")

    # Determine per-field confidence from the overall extraction confidence
    # Framework detection is structural (high when known, low when unknown)
    fw_confidence = "low" if framework_val in (None, "unknown", "generic") else raw_confidence
    # Input/output hints are interpretation of the framework + structure
    hint_confidence = "low" if framework_val in (None, "unknown") else (
        "high" if raw_confidence == "high" else "medium"
    )

    framework_fv = FieldValue(
        value=framework_val,
        source="extractor",
        confidence=fw_confidence,
    )
    input_hint_fv = FieldValue(
        value=input_hint_val,
        source="extractor",
        confidence=hint_confidence,
    )
    output_hint_fv = FieldValue(
        value=output_hint_val,
        source="extractor",
        confidence=hint_confidence,
    )

    # Promote load_format from extra to top-level FieldValue
    extra = data.get("extra", {})
    load_format_val = extra.pop("load_format", None)
    load_format_fv = None
    if load_format_val is not None:
        load_format_fv = FieldValue(
            value=load_format_val,
            source="extractor",
            confidence="high",
        )

    # Split confidence: inspection_confidence from raw extractor output,
    # interpretation_confidence from the hint derivation
    inspection_confidence = raw_confidence
    interpretation_confidence = hint_confidence

    meta = ArtifactMetadata(
        framework=framework_fv,
        class_name=data.get("class_name", "unknown"),
        class_hierarchy=data.get("class_hierarchy", []),
        input_hint=input_hint_fv,
        output_hint=output_hint_fv,
        feature_count=data.get("feature_count"),
        class_labels=data.get("class_labels"),
        artifact_path=data.get("artifact_path", abs_path),
        artifact_size_mb=data.get("artifact_size_mb", 0.0),
        extra=extra,
        raw_facts=data.get("raw_facts", {}),
        inspection_confidence=inspection_confidence,
        interpretation_confidence=interpretation_confidence,
        inspection_errors=data.get("inspection_errors", []),
        load_format=load_format_fv,
    )

    if "inspection_warning" in meta.extra:
        import warnings
        warnings.warn(
            f"Artifact inspection encountered an error and returned partial metadata: "
            f"{meta.extra['inspection_warning']}",
            stacklevel=2,
        )
    return meta
