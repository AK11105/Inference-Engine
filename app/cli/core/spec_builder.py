"""Deployment spec builder — derives a structured deployment candidate from raw_facts.

This module runs after Stage 1 extraction and BEFORE the LLM interpretation stage.
It produces a DeploymentSpecCandidate that tells the pipeline:
- What we already know (framework, artifact type, loader strategy, packages, capabilities)
- Whether interpretation is needed at all (deployment_readiness)

The LLM is only invoked when deployment_readiness != "ready".
"""
from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# DeploymentSpecCandidate — structured output of the spec builder
# ---------------------------------------------------------------------------

@dataclass
class DeploymentSpecCandidate:
    """Structured deployment metadata derived from raw extraction facts.

    Attributes:
        framework: Detected ML framework (e.g. "sklearn", "pytorch") or None.
        artifact_type: File format category (e.g. "pickle", "onnx") or None.
        loader_strategy: How to load the artifact (e.g. "joblib", "state_dict") or None.
        required_packages: Python packages needed at runtime.
        capabilities: Model capabilities detected (e.g. ["predict", "predict_proba"]).
        deployment_readiness: One of "ready", "needs_clarification", "unsupported".
    """

    framework: str | None
    artifact_type: str | None
    loader_strategy: str | None
    required_packages: list[str]
    capabilities: list[str]
    deployment_readiness: str  # "ready" | "needs_clarification" | "unsupported"


# ---------------------------------------------------------------------------
# _derive_readiness — explicit rule engine for deployment readiness
# ---------------------------------------------------------------------------

# Frameworks considered "unknown" / unresolved
_UNKNOWN_FRAMEWORKS = (None, "unknown", "generic")


def _derive_readiness(raw_facts: dict) -> str:
    """Derive deployment readiness from raw extraction facts.

    Rules (evaluated in priority order):
        1. format is missing or "unknown"  → "unsupported"
        2. framework is missing/unknown/generic → "needs_clarification"
        3. load_format (or load_via fallback) is missing/None → "needs_clarification"
        4. All three present and valid → "ready"
    """
    # Rule 1: format must be known
    fmt = raw_facts.get("format")
    if fmt is None or fmt == "unknown":
        return "unsupported"

    # Rule 2: framework must be resolved
    framework = raw_facts.get("framework")
    if framework in _UNKNOWN_FRAMEWORKS:
        return "needs_clarification"

    # Rule 3: load_format (or load_via fallback) must be present
    load_format = raw_facts.get("load_format") or raw_facts.get("load_via")
    if not load_format:
        return "needs_clarification"

    # All conditions met
    return "ready"


# ---------------------------------------------------------------------------
# Framework → required packages mapping
# ---------------------------------------------------------------------------

_FRAMEWORK_PACKAGES: dict[str, list[str]] = {
    "sklearn": ["scikit-learn", "joblib"],
    "pytorch": ["torch"],
    "transformers": ["transformers", "torch"],
    "onnx": ["onnxruntime"],
    "xgboost": ["xgboost", "joblib"],
    "lightgbm": ["lightgbm", "joblib"],
    "catboost": ["catboost", "joblib"],
    "sentence_transformers": ["sentence-transformers", "torch"],
    "safetensors": ["safetensors", "torch"],
}

# Format → artifact_type normalization (joblib is stored as pickle)
_FORMAT_TO_ARTIFACT_TYPE: dict[str, str] = {
    "pickle": "pickle",
    "joblib": "pickle",
    "pytorch": "pytorch",
    "onnx": "onnx",
    "safetensors": "safetensors",
    "directory": "directory",
}


# ---------------------------------------------------------------------------
# build_deployment_spec — main builder entry point
# ---------------------------------------------------------------------------

def build_deployment_spec(raw_facts: dict) -> DeploymentSpecCandidate:
    """Build a DeploymentSpecCandidate from raw extraction facts.

    This is a pure function — it does not mutate raw_facts.

    Args:
        raw_facts: Dict produced by Stage 1 artifact extraction.

    Returns:
        A fully populated DeploymentSpecCandidate.
    """
    # Derive readiness first (determines if LLM is needed)
    readiness = _derive_readiness(raw_facts)

    # Extract framework
    framework_raw = raw_facts.get("framework")
    framework = None if framework_raw in _UNKNOWN_FRAMEWORKS else framework_raw

    # Map format → artifact_type
    fmt = raw_facts.get("format", "unknown")
    artifact_type = _FORMAT_TO_ARTIFACT_TYPE.get(fmt)

    # Determine loader strategy (load_format preferred, load_via as fallback)
    loader_strategy = raw_facts.get("load_format") or raw_facts.get("load_via") or None

    # Determine required packages from framework
    required_packages: list[str] = []
    if framework and framework in _FRAMEWORK_PACKAGES:
        required_packages = list(_FRAMEWORK_PACKAGES[framework])

    # Derive capabilities from has_predict / has_predict_proba flags
    capabilities: list[str] = []
    if raw_facts.get("has_predict"):
        capabilities.append("predict")
    if raw_facts.get("has_predict_proba"):
        capabilities.append("predict_proba")

    return DeploymentSpecCandidate(
        framework=framework,
        artifact_type=artifact_type,
        loader_strategy=loader_strategy,
        required_packages=required_packages,
        capabilities=capabilities,
        deployment_readiness=readiness,
    )
