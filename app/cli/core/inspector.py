from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field

# Double-brace every dict/format literal inside the script so .format() ignores them.
# Only {path} is a real substitution placeholder.
_INSPECT_SCRIPT = """\
import os, json, sys, traceback as _tb

path = {path!r}
ext = os.path.splitext(path)[1].lower()

# ── ONNX: inspect without loading into Python ──────────────────────────────
if ext == ".onnx":
    try:
        import onnx
        model = onnx.load(path)
        inputs = [
            {{"name": i.name, "shape": list(i.type.tensor_type.shape.dim[j].dim_value for j in range(len(i.type.tensor_type.shape.dim)))}}
            for i in model.graph.input
        ]
        outputs = [
            {{"name": o.name, "shape": list(o.type.tensor_type.shape.dim[j].dim_value for j in range(len(o.type.tensor_type.shape.dim)))}}
            for o in model.graph.output
        ]
        extra = {{"onnx_inputs": inputs, "onnx_outputs": outputs}}
    except Exception:
        extra = {{}}
    result = dict(
        framework="onnx",
        class_name="ONNXModel",
        class_hierarchy=[],
        input_hint="numpy array matching ONNX input shape",
        output_hint="numpy array matching ONNX output shape",
        feature_count=None,
        class_labels=None,
        artifact_path=path,
        artifact_size_mb=round(os.path.getsize(path) / (1024 * 1024), 2),
        extra=extra,
    )
    print(json.dumps(result))
    sys.exit(0)

# ── pickle-based artifacts ──────────────────────────────────────────
try:
    import pickle

    with open(path, "rb") as f:
        obj = pickle.load(f)

    module = type(obj).__module__ or ""
    class_name = type(obj).__name__

    # ── framework detection (order matters) ──────────────────────────────────
    framework = "generic"
    extra = {{}}

    # sentence-transformers (check before transformers — it wraps HF models)
    try:
        from sentence_transformers import SentenceTransformer
        if isinstance(obj, SentenceTransformer):
            framework = "sentence_transformers"
    except Exception:
        pass

    # transformers PreTrainedModel
    if framework == "generic":
        try:
            from transformers import PreTrainedModel
            if isinstance(obj, PreTrainedModel):
                framework = "transformers"
        except Exception:
            pass

    # PyTorch nn.Module
    if framework == "generic":
        try:
            import torch
            if isinstance(obj, torch.nn.Module):
                framework = "pytorch"
        except Exception:
            pass

    # XGBoost
    if framework == "generic":
        try:
            import xgboost as xgb
            if isinstance(obj, (xgb.XGBModel, xgb.Booster)):
                framework = "xgboost"
        except Exception:
            pass

    # LightGBM
    if framework == "generic":
        try:
            import lightgbm as lgb
            if isinstance(obj, (lgb.Booster, lgb.LGBMModel)):
                framework = "lightgbm"
        except Exception:
            pass

    # CatBoost
    if framework == "generic":
        try:
            from catboost import CatBoost
            if isinstance(obj, CatBoost):
                framework = "catboost"
        except Exception:
            pass

    # sklearn (last — many frameworks inherit from sklearn base)
    if framework == "generic" and "sklearn" in module:
        framework = "sklearn"

    # ── metadata extraction ─────────────────────────────────────────────────
    class_hierarchy = []
    input_hint = "unknown"
    output_hint = "unknown"
    feature_count = None
    class_labels = None

    if framework == "sklearn":
        if hasattr(obj, "steps"):
            class_hierarchy = [type(s).__name__ for _, s in obj.steps]
        else:
            class_hierarchy = [class_name]

        if hasattr(obj, "n_features_in_"):
            feature_count = int(obj.n_features_in_)

        if hasattr(obj, "classes_"):
            class_labels = obj.classes_.tolist()
        elif hasattr(obj, "steps"):
            for _, step in obj.steps:
                if hasattr(step, "classes_"):
                    class_labels = step.classes_.tolist()
                    break

        text_vectorizers = ("TfidfVectorizer", "CountVectorizer", "HashingVectorizer")
        if class_hierarchy and class_hierarchy[0] in text_vectorizers:
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
        try:
            import torch
            layer_count = sum(1 for _ in obj.modules())
            extra["layer_count"] = layer_count
            children = list(obj.named_children())
            if children:
                extra["first_layer"] = type(children[0][1]).__name__
                extra["last_layer"] = type(children[-1][1]).__name__
        except Exception:
            pass
        input_hint = "torch.Tensor"
        output_hint = "torch.Tensor"

    elif framework == "transformers":
        try:
            cfg = obj.config
            extra["model_type"] = getattr(cfg, "model_type", "unknown")
            extra["hidden_size"] = getattr(cfg, "hidden_size", None)
            extra["num_labels"] = getattr(cfg, "num_labels", None)
            extra["tokenizer_class"] = getattr(cfg, "tokenizer_class", None)
        except Exception:
            pass
        input_hint = "dict with input_ids, attention_mask (tokenized)"
        output_hint = "ModelOutput (logits or last_hidden_state)"

    elif framework == "xgboost":
        try:
            import xgboost as xgb
            if isinstance(obj, xgb.XGBModel):
                extra["n_estimators"] = getattr(obj, "n_estimators", None)
                extra["objective"] = getattr(obj, "objective", None)
                if hasattr(obj, "n_features_in_"):
                    feature_count = int(obj.n_features_in_)
            elif isinstance(obj, xgb.Booster):
                extra["num_trees"] = obj.num_trees()
        except Exception:
            pass
        input_hint = "numpy array or pandas DataFrame"
        output_hint = "numpy array of predictions"

    elif framework == "lightgbm":
        try:
            import lightgbm as lgb
            if isinstance(obj, lgb.LGBMModel):
                extra["n_estimators"] = getattr(obj, "n_estimators", None)
                extra["objective"] = getattr(obj, "objective", None)
                if hasattr(obj, "n_features_in_"):
                    feature_count = int(obj.n_features_in_)
            elif isinstance(obj, lgb.Booster):
                extra["num_trees"] = obj.num_trees()
        except Exception:
            pass
        input_hint = "numpy array or pandas DataFrame"
        output_hint = "numpy array of predictions"

    elif framework == "catboost":
        try:
            from catboost import CatBoost
            extra["loss_function"] = obj.get_param("loss_function")
            fc = obj.get_param("feature_count") or obj.get_param("num_features")
            if fc is not None:
                feature_count = int(fc)
        except Exception:
            pass
        input_hint = "numpy array or pandas DataFrame"
        output_hint = "numpy array of predictions"

    elif framework == "sentence_transformers":
        try:
            extra["model_name"] = getattr(obj, "_model_card_text", None) or class_name
            modules = list(obj.modules())
            for m in modules:
                if hasattr(m, "word_embedding_dimension"):
                    extra["embedding_dim"] = m.word_embedding_dimension
                    break
        except Exception:
            pass
        input_hint = "string or list of strings"
        output_hint = "numpy array of shape (n, embedding_dim)"

    artifact_size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
    print(json.dumps(dict(
        framework=framework,
        class_name=class_name,
        class_hierarchy=class_hierarchy,
        input_hint=input_hint,
        output_hint=output_hint,
        feature_count=feature_count,
        class_labels=class_labels,
        artifact_path=path,
        artifact_size_mb=artifact_size_mb,
        extra=extra,
    )))
except Exception as _exc:
    _size = 0.0
    try:
        _size = round(os.path.getsize(path) / (1024 * 1024), 2)
    except Exception:
        pass
    print(json.dumps(dict(
        framework="unknown",
        class_name="unknown",
        class_hierarchy=[],
        input_hint="unknown",
        output_hint="unknown",
        feature_count=None,
        class_labels=None,
        artifact_path=path,
        artifact_size_mb=_size,
        extra={{"inspection_warning": str(_exc), "traceback": _tb.format_exc()}},
    )))
"""


@dataclass
class ArtifactMetadata:
    framework: str
    class_name: str
    class_hierarchy: list
    input_hint: str
    output_hint: str
    feature_count: int | None
    class_labels: list | None
    artifact_path: str
    artifact_size_mb: float
    extra: dict = field(default_factory=dict)


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
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"Inspection failed:\n{result.stderr.strip()}")

    data = json.loads(result.stdout)
    meta = ArtifactMetadata(**data)
    if "inspection_warning" in meta.extra:
        import warnings
        warnings.warn(
            f"Artifact inspection encountered an error and returned partial metadata: "
            f"{meta.extra['inspection_warning']}",
            stacklevel=2,
        )
    return meta
