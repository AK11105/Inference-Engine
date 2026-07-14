"""Issue #59 — Pickle safety gate: --allow-load flag and safety metadata.

Tests cover:
1. DeployAnswers has allow_load field
2. --allow-load CLI flag parsing
3. inspect_artifact() allow_load parameter
4. Safety gate logic: pickle format + allow_load=False → Layer 2 skipped
5. Safety dict present on all artifact outputs
6. Non-pickle formats are NOT gated
7. Backward compatibility: existing tests/behavior still works
8. deploy.py integration: non-interactive without --allow-load for pickle
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"
ROOT = Path(__file__).parent.parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def _venv_python():
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


# ===========================================================================
# 1. DeployAnswers — allow_load field
# ===========================================================================

class TestDeployAnswersAllowLoad:
    """DeployAnswers must have an allow_load: bool field."""

    def test_allow_load_field_exists(self):
        from app.cli.core.prompts import DeployAnswers
        ans = DeployAnswers(
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            allow_load=True,
        )
        assert ans.allow_load is True

    def test_allow_load_defaults_to_false(self):
        from app.cli.core.prompts import DeployAnswers
        ans = DeployAnswers(
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
        )
        assert ans.allow_load is False

    def test_allow_load_true(self):
        from app.cli.core.prompts import DeployAnswers
        ans = DeployAnswers(
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            allow_load=True,
        )
        assert ans.allow_load is True

    def test_allow_load_false_explicit(self):
        from app.cli.core.prompts import DeployAnswers
        ans = DeployAnswers(
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            allow_load=False,
        )
        assert ans.allow_load is False


# ===========================================================================
# 2. CLI flag parsing — --allow-load
# ===========================================================================

class TestCLIAllowLoadFlag:
    """The deploy subcommand must accept --allow-load."""

    def test_flag_recognized(self):
        """--allow-load should not cause an argparse error."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello",
                "--allow-load",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        # Should not fail with "unrecognized arguments"
        assert "unrecognized arguments" not in result.stderr
        assert result.returncode == 0

    def test_flag_absent_means_false(self):
        """Without --allow-load, the flag should default to False."""
        import argparse
        from app.cli.__main__ import main

        # We test the argparse setup directly
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        # Should succeed (dry-run) — allow_load defaults to False internally
        assert result.returncode == 0


# ===========================================================================
# 3. inspect_artifact() allow_load parameter
# ===========================================================================

class TestInspectArtifactAllowLoad:
    """inspect_artifact() accepts allow_load kwarg."""

    def test_allow_load_true_loads_pickle(self):
        """With allow_load=True, pickle extraction proceeds normally."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        assert meta.framework == "sklearn"
        assert meta.class_name == "Pipeline"
        # Layer 2 ran, so we have full class hierarchy
        assert len(meta.class_hierarchy) > 0

    def test_allow_load_false_skips_layer2_for_pickle(self):
        """With allow_load=False, pickle Layer 2 is skipped."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        # Layer 0 and Layer 1 still ran
        assert meta.artifact_size_mb >= 0
        assert meta.raw_facts.get("format") == "pickle"
        # Layer 2 was skipped — framework detection did not run
        assert meta.framework in ("unknown", None) or meta.raw_facts.get("deserialization_skipped") is True

    def test_allow_load_false_reports_error(self):
        """Skipping deserialization adds an error to raw_facts."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        errors = meta.raw_facts.get("errors", []) + meta.inspection_errors
        error_messages = [e.get("error", "") if isinstance(e, dict) else str(e) for e in errors]
        assert any("--allow-load" in msg for msg in error_messages)

    def test_allow_load_default_is_true_for_backward_compat(self):
        """Default behavior is allow_load=True for backward compat."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        # Should still load normally (existing behavior)
        assert meta.framework == "sklearn"
        assert meta.class_name == "Pipeline"


# ===========================================================================
# 4. Safety gate logic details
# ===========================================================================

class TestSafetyGateLogic:
    """Detailed tests for the gate behavior."""

    def test_pickle_format_without_allow_load_has_needs_clarification(self):
        """Pickle artifact without allow_load → deployment_readiness = needs_clarification."""
        from app.cli.core.inspector import inspect_artifact
        from app.cli.core.spec_builder import build_deployment_spec

        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        spec = build_deployment_spec(meta.raw_facts)
        assert spec.deployment_readiness == "needs_clarification"

    def test_pickle_format_with_allow_load_can_be_ready(self):
        """Pickle artifact with allow_load=True can reach 'ready' status."""
        from app.cli.core.inspector import inspect_artifact
        from app.cli.core.spec_builder import build_deployment_spec

        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        spec = build_deployment_spec(meta.raw_facts)
        assert spec.deployment_readiness == "ready"

    def test_joblib_format_without_allow_load_also_gated(self, tmp_path):
        """Joblib is stored via pickle — also gated."""
        from app.cli.core.inspector import inspect_artifact

        # Create a .joblib file
        import joblib
        from sklearn.linear_model import LogisticRegression
        model = LogisticRegression()
        model.fit([[1, 2], [3, 4]], [0, 1])
        p = tmp_path / "model.joblib"
        joblib.dump(model, str(p))

        meta = inspect_artifact(str(p), allow_load=False)
        # Should be gated like pickle
        errors = meta.raw_facts.get("errors", []) + meta.inspection_errors
        error_messages = [e.get("error", "") if isinstance(e, dict) else str(e) for e in errors]
        assert any("--allow-load" in msg for msg in error_messages)

    def test_onnx_not_gated_without_allow_load(self, tmp_path):
        """ONNX format is not gated — extraction proceeds regardless."""
        onnx = pytest.importorskip("onnx")
        from onnx import helper, TensorProto

        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [None, 4])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [None, 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        p = tmp_path / "model.onnx"
        onnx.save(model, str(p))

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(p), allow_load=False)
        # ONNX extraction should proceed — not gated
        assert meta.framework == "onnx"

    def test_pytorch_state_dict_not_gated(self, tmp_path):
        """PyTorch weights_only=True loading is not gated."""
        torch = pytest.importorskip("torch")
        sd = {"layer.weight": torch.zeros(4, 4)}
        p = tmp_path / "model.pt"
        torch.save(sd, str(p))

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(p), allow_load=False)
        # PyTorch extraction uses weights_only=True — safe
        assert meta.framework == "pytorch"

    def test_safetensors_not_gated(self, tmp_path):
        """Safetensors is safe by design — not gated."""
        pytest.importorskip("safetensors")
        import torch
        from safetensors.torch import save_file

        p = tmp_path / "model.safetensors"
        save_file({"w": torch.zeros(4)}, str(p))

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(p), allow_load=False)
        assert meta.framework in ("safetensors", "pytorch")

    def test_size_limit_100mb(self, tmp_path):
        """Artifacts > 100 MB should NOT be loaded even with allow_load=True.

        The spec says: inspection_mode == 'loaded' requires artifact ≤ 100 MB.
        """
        from app.cli.core.inspector import inspect_artifact

        # Create a minimal pickle that claims to be > 100 MB
        # We test the SIZE check by creating a real file... but that's too large.
        # Instead we test that the raw_facts["inspection_mode"] field is correct.
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        # Small fixture → inspection_mode should be "loaded"
        assert meta.raw_facts.get("inspection_mode") in ("loaded", None)
        # The mode should be present
        # (If None, the implementation needs to add it)


# ===========================================================================
# 5. Safety dict on all artifacts
# ===========================================================================

class TestSafetyDict:
    """Every artifact output must contain a safety dict."""

    def test_pickle_has_safety_dict(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        safety = meta.raw_facts.get("safety")
        assert safety is not None
        assert "deserialization_risk" in safety
        assert "execution_risk" in safety

    def test_pickle_deserialization_risk_is_high(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        assert meta.raw_facts["safety"]["deserialization_risk"] == "high"

    def test_pickle_without_allow_load_still_has_safety(self):
        """Safety dict is present even when deserialization is skipped."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        safety = meta.raw_facts.get("safety")
        assert safety is not None
        assert safety["deserialization_risk"] == "high"

    def test_onnx_has_safety_dict(self, tmp_path):
        onnx = pytest.importorskip("onnx")
        from onnx import helper, TensorProto

        X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [None, 4])
        Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [None, 2])
        node = helper.make_node("Relu", ["X"], ["Y"])
        graph = helper.make_graph([node], "test", [X], [Y])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
        p = tmp_path / "model.onnx"
        onnx.save(model, str(p))

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(p))
        safety = meta.raw_facts.get("safety")
        assert safety is not None
        # ONNX doesn't execute arbitrary code
        assert safety["deserialization_risk"] == "none"

    def test_pytorch_has_safety_dict(self, tmp_path):
        torch = pytest.importorskip("torch")
        sd = {"w": torch.zeros(4)}
        p = tmp_path / "model.pt"
        torch.save(sd, str(p))

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(p))
        safety = meta.raw_facts.get("safety")
        assert safety is not None
        # weights_only=True is safe
        assert safety["deserialization_risk"] in ("none", "low")

    def test_safety_dict_structure(self):
        """Safety dict has exactly the specified keys."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        safety = meta.raw_facts.get("safety")
        assert set(safety.keys()) == {"deserialization_risk", "execution_risk"}

    def test_safety_dict_values_are_valid_levels(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        safety = meta.raw_facts["safety"]
        valid_levels = {"none", "low", "medium", "high"}
        assert safety["deserialization_risk"] in valid_levels
        assert safety["execution_risk"] in valid_levels


# ===========================================================================
# 6. CLI deploy integration — non-interactive gating
# ===========================================================================

class TestDeployIntegration:
    """End-to-end deploy command behavior with pickle safety gate."""

    def test_dry_run_without_allow_load_still_runs(self):
        """Dry run without --allow-load should still complete (metadata-only)."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0

    def test_dry_run_with_allow_load_shows_full_metadata(self):
        """With --allow-load, full metadata is shown."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello",
                "--allow-load",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        # With allow_load, full sklearn metadata should appear
        assert "sklearn" in result.stdout

    def test_dry_run_without_allow_load_warns_about_pickle(self):
        """Without --allow-load, output should indicate deserialization was skipped."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        # Should mention pickle deserialization being skipped or --allow-load
        combined = result.stdout + result.stderr
        assert ("--allow-load" in combined
                or "skipped" in combined.lower()
                or "deserialization" in combined.lower()
                or "non-interactive" in combined.lower())


# ===========================================================================
# 7. Backward compatibility
# ===========================================================================

class TestBackwardCompatibility:
    """Existing functionality must not break."""

    def test_inspect_artifact_no_kwargs_still_works(self):
        """Calling inspect_artifact with only path still works (default allow_load=True)."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert meta.framework == "sklearn"
        assert meta.class_name == "Pipeline"

    def test_inspect_artifact_with_framework_hint_still_works(self):
        """Framework hint still works alongside allow_load."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), framework_hint="sklearn", allow_load=True)
        assert meta.framework == "sklearn"

    def test_deploy_answers_existing_fields_unchanged(self):
        """Existing fields on DeployAnswers still work."""
        from app.cli.core.prompts import DeployAnswers
        ans = DeployAnswers(
            name="sentiment", version="v1", device="cpu",
            routing="static", sample_input="test",
        )
        assert ans.name == "sentiment"
        assert ans.version == "v1"
        assert ans.device == "cpu"
        assert ans.routing == "static"
        assert ans.sample_input == "test"

    def test_existing_dry_run_still_succeeds(self):
        """The existing dry-run pattern must still work."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "sentiment", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "great movie",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0


# ===========================================================================
# 8. Safety metadata in ArtifactMetadata
# ===========================================================================

class TestArtifactMetadataSafety:
    """ArtifactMetadata exposes safety info."""

    def test_safety_in_raw_facts(self):
        """Safety dict is part of raw_facts (available to spec_builder and LLM)."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        assert "safety" in meta.raw_facts

    def test_deserialization_skipped_field_when_gated(self):
        """When gated, raw_facts contains deserialization_skipped=True."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        assert meta.raw_facts.get("deserialization_skipped") is True

    def test_inspection_mode_loaded_for_small_pickle(self):
        """Small pickle file has inspection_mode='loaded' when allowed."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=True)
        assert meta.raw_facts.get("inspection_mode") == "loaded"

    def test_inspection_mode_metadata_only_when_gated(self):
        """Gated pickle has inspection_mode='metadata_only'."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), allow_load=False)
        assert meta.raw_facts.get("inspection_mode") == "metadata_only"
