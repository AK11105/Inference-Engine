"""Issue #58 — DeploymentSpecCandidate builder and _derive_readiness rules.

TDD red-phase tests: these define the expected behavior of:
- DeploymentSpecCandidate dataclass
- _derive_readiness(raw_facts) rule engine
- build_deployment_spec(raw_facts) builder function

All tests should FAIL with ImportError before implementation and PASS after.
"""
from __future__ import annotations

import pytest


# ===========================================================================
# Part 1: DeploymentSpecCandidate dataclass
# ===========================================================================

class TestDeploymentSpecCandidateCreation:
    """DeploymentSpecCandidate can be instantiated with all expected fields."""

    def test_basic_creation_all_fields(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework="sklearn",
            artifact_type="pickle",
            loader_strategy="joblib",
            required_packages=["scikit-learn", "joblib"],
            capabilities=["predict", "predict_proba"],
            deployment_readiness="ready",
        )
        assert spec.framework == "sklearn"
        assert spec.artifact_type == "pickle"
        assert spec.loader_strategy == "joblib"
        assert spec.required_packages == ["scikit-learn", "joblib"]
        assert spec.capabilities == ["predict", "predict_proba"]
        assert spec.deployment_readiness == "ready"

    def test_nullable_fields_accept_none(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework=None,
            artifact_type=None,
            loader_strategy=None,
            required_packages=[],
            capabilities=[],
            deployment_readiness="needs_clarification",
        )
        assert spec.framework is None
        assert spec.artifact_type is None
        assert spec.loader_strategy is None

    def test_is_dataclass(self):
        from dataclasses import is_dataclass
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        assert is_dataclass(DeploymentSpecCandidate)

    def test_required_packages_defaults_to_empty_list(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework="sklearn",
            artifact_type="pickle",
            loader_strategy="joblib",
            required_packages=[],
            capabilities=[],
            deployment_readiness="ready",
        )
        assert spec.required_packages == []

    def test_capabilities_defaults_to_empty_list(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework="pytorch",
            artifact_type="pytorch",
            loader_strategy="torch_load",
            required_packages=["torch"],
            capabilities=[],
            deployment_readiness="ready",
        )
        assert spec.capabilities == []


class TestDeploymentSpecCandidateReadinessValues:
    """deployment_readiness must be one of the three valid values."""

    def test_ready_is_valid(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework="sklearn",
            artifact_type="pickle",
            loader_strategy="joblib",
            required_packages=[],
            capabilities=[],
            deployment_readiness="ready",
        )
        assert spec.deployment_readiness == "ready"

    def test_needs_clarification_is_valid(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework=None,
            artifact_type="pickle",
            loader_strategy=None,
            required_packages=[],
            capabilities=[],
            deployment_readiness="needs_clarification",
        )
        assert spec.deployment_readiness == "needs_clarification"

    def test_unsupported_is_valid(self):
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        spec = DeploymentSpecCandidate(
            framework=None,
            artifact_type=None,
            loader_strategy=None,
            required_packages=[],
            capabilities=[],
            deployment_readiness="unsupported",
        )
        assert spec.deployment_readiness == "unsupported"


# ===========================================================================
# Part 2: _derive_readiness rule engine
# ===========================================================================

class TestDeriveReadinessUnsupported:
    """format == 'unknown' → 'unsupported'."""

    def test_unknown_format_returns_unsupported(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "unknown",
            "framework": "sklearn",
            "load_format": "joblib",
        }
        assert _derive_readiness(raw_facts) == "unsupported"

    def test_unknown_format_overrides_valid_framework(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "unknown",
            "framework": "pytorch",
            "load_format": "state_dict",
        }
        assert _derive_readiness(raw_facts) == "unsupported"

    def test_missing_format_key_returns_unsupported(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {"framework": "sklearn", "load_format": "joblib"}
        assert _derive_readiness(raw_facts) == "unsupported"


class TestDeriveReadinessNeedsClarification:
    """framework is None/unknown OR load_format is None → 'needs_clarification'."""

    def test_none_framework_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": None,
            "load_format": "joblib",
        }
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_unknown_framework_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "unknown",
            "load_format": "pickle",
        }
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_missing_framework_key_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {"format": "pickle", "load_format": "joblib"}
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_none_load_format_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": None,
        }
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_missing_load_format_key_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
        }
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_generic_framework_returns_needs_clarification(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "generic",
            "load_format": "pickle",
        }
        assert _derive_readiness(raw_facts) == "needs_clarification"


class TestDeriveReadinessReady:
    """format known + framework known + load_format known → 'ready'."""

    def test_sklearn_pickle_ready(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
        }
        assert _derive_readiness(raw_facts) == "ready"

    def test_pytorch_state_dict_ready(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pytorch",
            "framework": "pytorch",
            "load_format": "state_dict",
        }
        assert _derive_readiness(raw_facts) == "ready"

    def test_onnx_ready(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "onnx",
            "framework": "onnx",
            "load_format": "onnx_session",
        }
        assert _derive_readiness(raw_facts) == "ready"

    def test_transformers_directory_ready(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "directory",
            "framework": "transformers",
            "load_format": "from_pretrained",
        }
        assert _derive_readiness(raw_facts) == "ready"

    def test_xgboost_ready(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "xgboost",
            "load_format": "joblib",
        }
        assert _derive_readiness(raw_facts) == "ready"


class TestDeriveReadinessEdgeCases:
    """Edge cases and rule priority."""

    def test_format_unknown_takes_priority_over_missing_framework(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {"format": "unknown", "framework": None, "load_format": None}
        # First rule wins: format == "unknown" → "unsupported"
        assert _derive_readiness(raw_facts) == "unsupported"

    def test_empty_raw_facts_returns_unsupported(self):
        from app.cli.core.spec_builder import _derive_readiness

        assert _derive_readiness({}) == "unsupported"

    def test_errors_in_raw_facts_do_not_affect_readiness_directly(self):
        from app.cli.core.spec_builder import _derive_readiness

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "errors": [{"layer": "deep", "error": "some warning"}],
        }
        # Errors don't change readiness if all three keys are valid
        assert _derive_readiness(raw_facts) == "ready"


# ===========================================================================
# Part 3: build_deployment_spec builder function
# ===========================================================================

class TestBuildDeploymentSpecFrameworkMapping:
    """build_deployment_spec correctly maps raw_facts framework to spec fields."""

    def test_sklearn_pickle(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "has_predict": True,
            "has_predict_proba": True,
            "class_name": "Pipeline",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "sklearn"
        assert spec.artifact_type == "pickle"
        assert spec.loader_strategy == "joblib"
        assert "scikit-learn" in spec.required_packages
        assert "predict" in spec.capabilities
        assert "predict_proba" in spec.capabilities
        assert spec.deployment_readiness == "ready"

    def test_pytorch_state_dict(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pytorch",
            "framework": "pytorch",
            "load_format": "state_dict",
            "has_predict": False,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "pytorch"
        assert spec.artifact_type == "pytorch"
        assert spec.loader_strategy == "state_dict"
        assert "torch" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_pytorch_full_model(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pytorch",
            "framework": "pytorch",
            "load_format": "full_model",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "pytorch"
        assert spec.loader_strategy == "full_model"
        assert "torch" in spec.required_packages

    def test_onnx(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "onnx",
            "framework": "onnx",
            "load_format": "onnx_session",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "onnx"
        assert spec.artifact_type == "onnx"
        assert "onnxruntime" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_transformers_directory(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "directory",
            "framework": "transformers",
            "load_format": "from_pretrained",
            "is_directory": True,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "transformers"
        assert spec.artifact_type == "directory"
        assert "transformers" in spec.required_packages
        assert "torch" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_xgboost(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "xgboost",
            "load_format": "joblib",
            "has_predict": True,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "xgboost"
        assert spec.artifact_type == "pickle"
        assert "xgboost" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_lightgbm(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "lightgbm",
            "load_format": "joblib",
            "has_predict": True,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "lightgbm"
        assert "lightgbm" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_catboost(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "catboost",
            "load_format": "joblib",
            "has_predict": True,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "catboost"
        assert "catboost" in spec.required_packages

    def test_sentence_transformers(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sentence_transformers",
            "load_format": "pickle",
            "has_predict": False,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "sentence_transformers"
        assert "sentence-transformers" in spec.required_packages

    def test_safetensors(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "safetensors",
            "framework": "safetensors",
            "load_format": "safetensors_open",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "safetensors"
        assert "safetensors" in spec.required_packages


class TestBuildDeploymentSpecCapabilities:
    """build_deployment_spec derives capabilities from raw_facts."""

    def test_has_predict_adds_predict_capability(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "has_predict": True,
            "has_predict_proba": False,
        }
        spec = build_deployment_spec(raw_facts)
        assert "predict" in spec.capabilities
        assert "predict_proba" not in spec.capabilities

    def test_has_predict_proba_adds_both_capabilities(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "has_predict": True,
            "has_predict_proba": True,
        }
        spec = build_deployment_spec(raw_facts)
        assert "predict" in spec.capabilities
        assert "predict_proba" in spec.capabilities

    def test_no_predict_gives_empty_capabilities(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pytorch",
            "framework": "pytorch",
            "load_format": "state_dict",
            "has_predict": False,
        }
        spec = build_deployment_spec(raw_facts)
        assert "predict" not in spec.capabilities

    def test_missing_has_predict_key_gives_empty_capabilities(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "onnx",
            "framework": "onnx",
            "load_format": "onnx_session",
        }
        spec = build_deployment_spec(raw_facts)
        # No has_predict key → no predict capability inferred
        assert "predict" not in spec.capabilities


class TestBuildDeploymentSpecLoaderStrategy:
    """build_deployment_spec correctly maps load_format to loader_strategy."""

    def test_joblib_loader(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.loader_strategy == "joblib"

    def test_pickle_loader(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "pickle",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.loader_strategy == "pickle"

    def test_none_load_format_gives_none_strategy(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": None,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.loader_strategy is None
        assert spec.deployment_readiness == "needs_clarification"


class TestBuildDeploymentSpecArtifactType:
    """build_deployment_spec maps format to artifact_type."""

    def test_pickle_format(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {"format": "pickle", "framework": "sklearn", "load_format": "joblib"}
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type == "pickle"

    def test_pytorch_format(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {"format": "pytorch", "framework": "pytorch", "load_format": "state_dict"}
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type == "pytorch"

    def test_onnx_format(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {"format": "onnx", "framework": "onnx", "load_format": "onnx_session"}
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type == "onnx"

    def test_directory_format(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {"format": "directory", "framework": "transformers", "load_format": "from_pretrained"}
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type == "directory"

    def test_unknown_format_gives_none(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {"format": "unknown", "framework": "sklearn", "load_format": "joblib"}
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type is None
        assert spec.deployment_readiness == "unsupported"


# ===========================================================================
# Part 4: Integration tests — full pipeline from raw_facts to spec
# ===========================================================================

class TestBuildDeploymentSpecIntegration:
    """End-to-end: realistic raw_facts dicts from actual extraction produce correct specs."""

    def test_realistic_sklearn_pipeline_extraction(self):
        """Simulates raw_facts from inspecting tests/fixtures/sentiment.pkl."""
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "artifact_path": "/path/to/sentiment.pkl",
            "artifact_size_mb": 0.05,
            "extension": ".pkl",
            "is_directory": False,
            "errors": [],
            "format": "pickle",
            "load_via": "joblib",
            "class_name": "Pipeline",
            "module": "sklearn.pipeline",
            "attributes": ["steps", "memory", "verbose"],
            "has_predict": True,
            "has_predict_proba": True,
            "has_steps": True,
            "framework": "sklearn",
            "pipeline_steps": ["TfidfVectorizer", "LogisticRegression"],
            "n_features_in": 12,
            "classes": [0, 1],
            "confidence": "high",
            "load_format": "joblib",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "sklearn"
        assert spec.artifact_type == "pickle"
        assert spec.loader_strategy == "joblib"
        assert "scikit-learn" in spec.required_packages
        assert "predict" in spec.capabilities
        assert "predict_proba" in spec.capabilities
        assert spec.deployment_readiness == "ready"

    def test_realistic_pytorch_state_dict(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "artifact_path": "/path/to/model.pt",
            "artifact_size_mb": 45.2,
            "extension": ".pt",
            "is_directory": False,
            "errors": [],
            "format": "pytorch",
            "framework": "pytorch",
            "load_format": "state_dict",
            "state_dict_keys": ["layer1.weight", "layer1.bias"],
            "param_count": 1024,
            "confidence": "high",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "pytorch"
        assert spec.artifact_type == "pytorch"
        assert spec.loader_strategy == "state_dict"
        assert "torch" in spec.required_packages
        assert spec.deployment_readiness == "ready"

    def test_realistic_unknown_format(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "artifact_path": "/path/to/model.xyz",
            "artifact_size_mb": 1.0,
            "extension": ".xyz",
            "is_directory": False,
            "errors": [{"layer": "extraction", "error": "cannot load"}],
            "format": "unknown",
            "framework": "unknown",
            "confidence": "low",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.deployment_readiness == "unsupported"
        assert spec.framework is None or spec.framework == "unknown"

    def test_realistic_partial_extraction_missing_load_format(self):
        """High-confidence sklearn detection but missing load_format → needs_clarification."""
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "class_name": "SGDClassifier",
            "module": "sklearn.linear_model",
            "has_predict": True,
            "confidence": "high",
            # load_format is missing — extractor couldn't determine it
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "sklearn"
        assert spec.deployment_readiness == "needs_clarification"


# ===========================================================================
# Part 5: Backward compatibility — build_deployment_spec doesn't mutate input
# ===========================================================================

class TestBuildDeploymentSpecPurity:
    """build_deployment_spec does not mutate the input raw_facts dict."""

    def test_does_not_mutate_input(self):
        from app.cli.core.spec_builder import build_deployment_spec
        import copy

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "has_predict": True,
        }
        original = copy.deepcopy(raw_facts)
        build_deployment_spec(raw_facts)
        assert raw_facts == original

    def test_returns_new_instance_each_call(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
        }
        spec1 = build_deployment_spec(raw_facts)
        spec2 = build_deployment_spec(raw_facts)
        assert spec1 is not spec2
        assert spec1.deployment_readiness == spec2.deployment_readiness


# ===========================================================================
# Part 6: Edge cases and robustness
# ===========================================================================

class TestBuildDeploymentSpecEdgeCases:
    """Edge cases: empty dicts, extra keys, unusual values."""

    def test_empty_raw_facts(self):
        from app.cli.core.spec_builder import build_deployment_spec

        spec = build_deployment_spec({})
        assert spec.deployment_readiness == "unsupported"

    def test_extra_keys_ignored(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_format": "joblib",
            "unknown_key": "some_value",
            "another_key": 42,
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.deployment_readiness == "ready"

    def test_load_via_used_as_fallback_for_load_format(self):
        """If load_format is missing but load_via exists, it should be used."""
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "pickle",
            "framework": "sklearn",
            "load_via": "joblib",
            # No load_format key — but load_via exists from pickle extractor
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.loader_strategy == "joblib"
        assert spec.deployment_readiness == "ready"

    def test_joblib_format_treated_as_pickle_artifact(self):
        from app.cli.core.spec_builder import build_deployment_spec

        raw_facts = {
            "format": "joblib",
            "framework": "sklearn",
            "load_format": "joblib",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.artifact_type == "pickle"
        assert spec.deployment_readiness == "ready"
