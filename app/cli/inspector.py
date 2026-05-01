from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

# Double-brace every dict/format literal inside the script so .format() ignores them.
# Only {path} is a real substitution placeholder.
_INSPECT_SCRIPT = """\
import os, pickle, json, sys

path = {path!r}

with open(path, "rb") as f:
    obj = pickle.load(f)

module = type(obj).__module__ or ""
class_name = type(obj).__name__

if "sklearn" in module:
    framework = "sklearn"
elif "torch" in module:
    framework = "pytorch"
elif "xgboost" in module:
    framework = "xgboost"
else:
    framework = "generic"

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
    input_hint = "tensor"
    output_hint = "tensor"

artifact_size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)

result = dict(
    framework=framework,
    class_name=class_name,
    class_hierarchy=class_hierarchy,
    input_hint=input_hint,
    output_hint=output_hint,
    feature_count=feature_count,
    class_labels=class_labels,
    artifact_path=path,
    artifact_size_mb=artifact_size_mb,
)
print(json.dumps(result))
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
    return ArtifactMetadata(**data)
