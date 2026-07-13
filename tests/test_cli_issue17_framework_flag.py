"""Issue #17 — --framework flag on deploy.

Covers:
  1. inspect_artifact(path, framework_hint=...) records the hint in raw_facts
     and lets it win over a generic/unresolved structural detection.
  2. spec_builder uses framework_hint as a fallback (not an override) when
     structural detection failed, so deployment_readiness reflects it.
  3. CLI: --framework is parsed, validated, and threaded through to inspect_artifact.
"""
from __future__ import annotations

import pickle
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _venv_python():
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    return str(venv_python) if venv_python.exists() else sys.executable


# ===========================================================================
# 1. inspect_artifact(framework_hint=...)
# ===========================================================================

class TestInspectArtifactFrameworkHint:
    def test_no_hint_leaves_framework_from_extractor(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert meta.framework == "sklearn"
        assert meta.framework.source == "extractor"
        assert meta.raw_facts.get("framework_hint") is None

    def test_hint_recorded_in_raw_facts_before_extraction(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), framework_hint="sklearn")
        assert meta.raw_facts["framework_hint"] == "sklearn"

    def test_hint_wins_over_unresolved_structural_detection(self, tmp_path):
        """Simulates a missing optional dependency: the object's real framework
        can't be structurally identified (module doesn't match any detector,
        doesn't contain 'sklearn'), so extraction reports 'generic'."""
        # A plain dict has no framework-identifying module/isinstance match,
        # so structural detection falls back to "generic" — simulating a
        # missing optional dependency (e.g. xgboost not installed).
        obj = {"_type": "unknown_model"}
        pkl_path = tmp_path / "model.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(obj, f)

        from app.cli.core.inspector import inspect_artifact
        meta_without_hint = inspect_artifact(str(pkl_path))
        assert meta_without_hint.framework == "generic"

        meta_with_hint = inspect_artifact(str(pkl_path), framework_hint="xgboost")
        assert meta_with_hint.framework == "xgboost"
        assert meta_with_hint.framework.source == "user"

    def test_hint_does_not_suppress_structural_extraction(self, tmp_path):
        """Even with a hint, the extractor still runs and populates normal facts."""
        obj = {"_type": "unknown_model"}
        pkl_path = tmp_path / "model.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(obj, f)

        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(pkl_path), framework_hint="xgboost")
        assert meta.class_name == "dict"
        assert meta.raw_facts.get("class_name") == "dict"
        assert meta.raw_facts.get("errors") == []

    def test_hint_wins_even_over_confident_detection(self):
        """A --framework hint is trusted input: it always wins, even against
        a confidently (and correctly) detected framework."""
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE), framework_hint="pytorch")
        assert meta.framework == "pytorch"
        assert meta.framework.source == "user"
        # raw_facts still reflects the real, structurally-detected framework
        assert meta.raw_facts["framework"] == "sklearn"


# ===========================================================================
# 2. spec_builder honors framework_hint as a fallback
# ===========================================================================

class TestSpecBuilderFrameworkHint:
    def test_readiness_needs_clarification_without_hint(self):
        from app.cli.core.spec_builder import _derive_readiness
        raw_facts = {"format": "pickle", "framework": "generic", "load_via": "pickle"}
        assert _derive_readiness(raw_facts) == "needs_clarification"

    def test_readiness_ready_when_hint_fills_gap(self):
        from app.cli.core.spec_builder import _derive_readiness
        raw_facts = {
            "format": "pickle", "framework": "generic",
            "framework_hint": "xgboost", "load_via": "pickle",
        }
        assert _derive_readiness(raw_facts) == "ready"

    def test_hint_ignored_when_framework_already_resolved(self):
        """The hint only fills gaps — it never overrides a resolved framework
        fact in raw_facts (that fact stays the ground-truth extraction result)."""
        from app.cli.core.spec_builder import _derive_readiness, build_deployment_spec
        raw_facts = {
            "format": "pickle", "framework": "sklearn",
            "framework_hint": "pytorch", "load_via": "joblib",
        }
        assert _derive_readiness(raw_facts) == "ready"
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "sklearn"
        assert "scikit-learn" in spec.required_packages

    def test_build_deployment_spec_uses_hint_for_required_packages(self):
        from app.cli.core.spec_builder import build_deployment_spec
        raw_facts = {
            "format": "pickle", "framework": "unknown",
            "framework_hint": "lightgbm", "load_via": "pickle",
        }
        spec = build_deployment_spec(raw_facts)
        assert spec.framework == "lightgbm"
        assert "lightgbm" in spec.required_packages
        assert spec.deployment_readiness == "ready"


# ===========================================================================
# 3. CLI wiring
# ===========================================================================

class TestDeployCLIFrameworkFlag:
    def test_run_deploy_passes_framework_to_inspect_artifact(self, monkeypatch):
        from app.cli.commands import deploy as deploy_module
        from app.cli.core.inspector import inspect_artifact as real_inspect

        captured = {}

        def fake_inspect(path, **kwargs):
            captured["framework_hint"] = kwargs.get("framework_hint")
            return real_inspect(path)

        monkeypatch.setattr(deploy_module, "inspect_artifact", fake_inspect)
        deploy_module.run_deploy(str(FIXTURE), framework="xgboost", dry_run=True,
                                  name="x", version="v1", device="cpu",
                                  routing="static", sample_input="hi")
        assert captured["framework_hint"] == "xgboost"

    def test_cli_rejects_unknown_framework_choice(self):
        result = subprocess.run(
            [_venv_python(), "-m", "app.cli", "deploy", str(FIXTURE), "--framework", "not-a-real-framework"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_cli_framework_flag_overrides_preview_metadata(self):
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "sentiment", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "great movie",
                "--framework", "xgboost",
                "--dry-run",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert result.returncode == 0
        assert "xgboost" in result.stdout
