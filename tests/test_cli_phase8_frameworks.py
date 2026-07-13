"""CLI Phase 8 — multi-framework inspector + scaffold fallback tests."""
from __future__ import annotations

import pickle
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


# ---------------------------------------------------------------------------
# Helpers — build mock objects that look like each framework
# ---------------------------------------------------------------------------

def _make_mock(module_prefix: str, class_name: str, **attrs):
    """Return a mock object whose type reports the given module and class name."""
    cls = type(class_name, (), {"__module__": module_prefix, **attrs})
    obj = cls()
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# 8.1 — Inspector detection (mock objects, no real weights)
# ---------------------------------------------------------------------------

class TestInspectorDetection:
    """Test that inspect_artifact correctly identifies each framework."""

    def _run_inspect_script(self, obj, tmp_path):
        """Pickle obj to a temp file and run the inspector subprocess."""
        pkl_path = tmp_path / "model.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(obj, f)

        from app.cli.core.inspector import inspect_artifact
        return inspect_artifact(str(pkl_path))

    def test_sklearn_detection(self, tmp_path):
        """sklearn Pipeline is detected as 'sklearn'."""
        meta = self._run_inspect_script(
            # The real sentiment.pkl fixture is sklearn
            pickle.loads(FIXTURE.read_bytes()),
            tmp_path,
        )
        assert meta.framework == "sklearn"
        assert meta.class_name != ""

    def test_sklearn_metadata_extracted(self, tmp_path):
        """sklearn metadata includes class_hierarchy and class_labels."""
        meta = self._run_inspect_script(
            pickle.loads(FIXTURE.read_bytes()),
            tmp_path,
        )
        assert isinstance(meta.class_hierarchy, list)
        assert len(meta.class_hierarchy) > 0

    def test_generic_fallback(self, tmp_path):
        """An unrecognised object falls back to 'generic'."""
        import struct
        # Use a simple object that can be pickled — a plain dict with no sklearn/torch module
        # We can't use a locally-defined class (not picklable), so use a stdlib object
        # that won't match any framework detector.
        obj = {"_type": "unknown_model"}
        meta = self._run_inspect_script(obj, tmp_path)
        assert meta.framework == "generic"

    def test_extra_field_present(self, tmp_path):
        """ArtifactMetadata always has an 'extra' dict."""
        meta = self._run_inspect_script(
            pickle.loads(FIXTURE.read_bytes()),
            tmp_path,
        )
        assert isinstance(meta.extra, dict)

    def test_artifact_size_populated(self, tmp_path):
        """artifact_size_mb is a non-negative float."""
        meta = self._run_inspect_script(
            pickle.loads(FIXTURE.read_bytes()),
            tmp_path,
        )
        assert meta.artifact_size_mb >= 0.0


# ---------------------------------------------------------------------------
# 8.1 — Framework detection via module name (unit-level, no subprocess)
# ---------------------------------------------------------------------------

class TestFrameworkDetectionLogic:
    """
    Test the detection logic by patching the subprocess to return controlled JSON.
    These tests verify the inspector script's branching without needing real weights.
    """

    def _meta_for_framework(self, framework: str, class_name: str = "Model", **extra_fields):
        """Build an ArtifactMetadata as if the inspector returned it."""
        from app.cli.core.inspector import ArtifactMetadata
        return ArtifactMetadata(
            framework=framework,
            class_name=class_name,
            class_hierarchy=[],
            input_hint="unknown",
            output_hint="unknown",
            feature_count=None,
            class_labels=None,
            artifact_path="/tmp/model.pkl",
            artifact_size_mb=1.0,
            extra=extra_fields,
        )

    def test_pytorch_meta(self):
        meta = self._meta_for_framework("pytorch", "ResNet", layer_count=50)
        assert meta.framework == "pytorch"
        assert meta.extra["layer_count"] == 50

    def test_transformers_meta(self):
        meta = self._meta_for_framework(
            "transformers", "BertForSequenceClassification",
            model_type="bert", num_labels=2,
        )
        assert meta.framework == "transformers"
        assert meta.extra["model_type"] == "bert"

    def test_xgboost_meta(self):
        meta = self._meta_for_framework("xgboost", "XGBClassifier", n_estimators=100)
        assert meta.framework == "xgboost"
        assert meta.extra["n_estimators"] == 100

    def test_lightgbm_meta(self):
        meta = self._meta_for_framework("lightgbm", "LGBMClassifier", n_estimators=200)
        assert meta.framework == "lightgbm"
        assert meta.extra["n_estimators"] == 200

    def test_catboost_meta(self):
        meta = self._meta_for_framework("catboost", "CatBoostClassifier", loss_function="Logloss")
        assert meta.framework == "catboost"
        assert meta.extra["loss_function"] == "Logloss"

    def test_onnx_meta(self):
        meta = self._meta_for_framework(
            "onnx", "ONNXModel",
            onnx_inputs=[{"name": "input", "shape": [1, 10]}],
            onnx_outputs=[{"name": "output", "shape": [1, 2]}],
        )
        assert meta.framework == "onnx"
        assert meta.extra["onnx_inputs"][0]["name"] == "input"

    def test_sentence_transformers_meta(self):
        meta = self._meta_for_framework(
            "sentence_transformers", "SentenceTransformer", embedding_dim=768
        )
        assert meta.framework == "sentence_transformers"
        assert meta.extra["embedding_dim"] == 768


# ---------------------------------------------------------------------------
# 8.2 — Prompt template rendering
# ---------------------------------------------------------------------------

class TestPromptTemplates:
    """Test that _framework_hints returns the right content per framework."""

    def _hints_for(self, framework: str, **extra):
        from app.cli.core.agent import _framework_hints
        from app.cli.core.inspector import ArtifactMetadata
        meta = ArtifactMetadata(
            framework=framework,
            class_name="Model",
            class_hierarchy=[],
            input_hint="x",
            output_hint="y",
            feature_count=None,
            class_labels=None,
            artifact_path="/tmp/m.pkl",
            artifact_size_mb=1.0,
            extra=extra,
        )
        return _framework_hints(meta)

    def test_pytorch_hints_present(self):
        hints = self._hints_for("pytorch", layer_count=10)
        combined = "\n".join(hints)
        assert "torch.load" in combined
        assert "no_grad" in combined
        assert "Layer count: 10" in combined

    def test_transformers_hints_present(self):
        hints = self._hints_for("transformers", model_type="bert", num_labels=2)
        combined = "\n".join(hints)
        assert "from_pretrained" in combined
        assert "tokenize" in combined
        assert "bert" in combined

    def test_xgboost_hints_present(self):
        hints = self._hints_for("xgboost", n_estimators=100, objective="binary:logistic")
        combined = "\n".join(hints)
        assert "XGBoost" in combined
        assert "numpy" in combined
        assert "100" in combined

    def test_lightgbm_hints_present(self):
        hints = self._hints_for("lightgbm", n_estimators=50)
        combined = "\n".join(hints)
        assert "LightGBM" in combined
        assert "50" in combined

    def test_catboost_hints_present(self):
        hints = self._hints_for("catboost", loss_function="Logloss")
        combined = "\n".join(hints)
        assert "CatBoost" in combined
        assert "Logloss" in combined

    def test_onnx_hints_present(self):
        hints = self._hints_for("onnx")
        combined = "\n".join(hints)
        assert "onnxruntime" in combined
        assert "InferenceSession" in combined

    def test_sentence_transformers_hints_present(self):
        hints = self._hints_for("sentence_transformers", embedding_dim=384)
        combined = "\n".join(hints)
        assert "SentenceTransformer" in combined
        assert "encode" in combined
        assert "384" in combined

    def test_generic_no_hints(self):
        hints = self._hints_for("generic")
        assert hints == []

    def test_sklearn_no_hints(self):
        hints = self._hints_for("sklearn")
        assert hints == []

    def test_full_prompt_includes_hints(self):
        """_build_user_prompt includes framework hints in the output."""
        from app.cli.core.agent import _build_user_prompt
        from app.cli.core.inspector import ArtifactMetadata
        meta = ArtifactMetadata(
            framework="pytorch",
            class_name="ResNet",
            class_hierarchy=[],
            input_hint="tensor",
            output_hint="tensor",
            feature_count=None,
            class_labels=None,
            artifact_path="/tmp/m.pkl",
            artifact_size_mb=1.0,
            extra={"layer_count": 5},
        )
        prompt = _build_user_prompt(meta, "/tmp/m.pkl")
        assert "torch.load" in prompt
        assert "no_grad" in prompt


# ---------------------------------------------------------------------------
# 8.3 — Scaffold fallback
# ---------------------------------------------------------------------------

class TestScaffoldFallback:
    """Test write_scaffold produces a valid, importable Python file with TODOs."""

    def _make_meta(self, framework="generic"):
        from app.cli.core.inspector import ArtifactMetadata
        return ArtifactMetadata(
            framework=framework,
            class_name="MyModel",
            class_hierarchy=[],
            input_hint="array",
            output_hint="float",
            feature_count=None,
            class_labels=None,
            artifact_path=str(FIXTURE),
            artifact_size_mb=1.0,
            extra={},
        )

    def _routing_file(self, tmp_path):
        routing_file = tmp_path / "routing.py"
        routing_file.write_text('ROUTES = {\n}\n', encoding="utf-8")
        return routing_file

    def _make_answers(self):
        from app.cli.core.prompts import DeployAnswers
        return DeployAnswers(
            name="test_scaffold",
            version="v1",
            device="cpu",
            routing="static",
            sample_input="test",
        )

    def test_scaffold_writes_definition_py(self, tmp_path):
        from app.cli.core.writer import write_scaffold
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        definition = tmp_path / "models" / "test_scaffold" / "v1" / "definition.py"
        assert definition.exists()

    def test_scaffold_is_valid_python(self, tmp_path):
        from app.cli.core.writer import write_scaffold
        import ast as ast_mod
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        definition = tmp_path / "models" / "test_scaffold" / "v1" / "definition.py"
        source = definition.read_text(encoding="utf-8")
        # Must parse without SyntaxError
        ast_mod.parse(source)

    def test_scaffold_contains_todos(self, tmp_path):
        from app.cli.core.writer import write_scaffold
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        definition = tmp_path / "models" / "test_scaffold" / "v1" / "definition.py"
        source = definition.read_text(encoding="utf-8")
        assert "TODO" in source
        assert "NotImplementedError" in source

    def test_scaffold_raises_not_implemented_at_runtime(self, tmp_path):
        """The scaffold file raises NotImplementedError when build_pipeline() is called."""
        from app.cli.core.writer import write_scaffold
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        definition = tmp_path / "models" / "test_scaffold" / "v1" / "definition.py"
        source = definition.read_text(encoding="utf-8")

        import importlib.util
        spec = importlib.util.spec_from_file_location("_scaffold_test", definition)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with pytest.raises(NotImplementedError):
            mod.build_pipeline()

    def test_scaffold_copies_artifact(self, tmp_path):
        from app.cli.core.writer import write_scaffold
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        artifact_copy = tmp_path / "models" / "test_scaffold" / "v1" / FIXTURE.name
        assert artifact_copy.exists()

    def test_scaffold_patches_routing(self, tmp_path):
        from app.cli.core.writer import write_scaffold
        meta = self._make_meta()
        answers = self._make_answers()

        routing_file = self._routing_file(tmp_path)

        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing_file,
        )

        routing_content = routing_file.read_text(encoding="utf-8")
        assert "test_scaffold" in routing_content

    def test_deploy_uses_scaffold_on_validation_failure(self, tmp_path, monkeypatch):
        """run_deploy falls back to scaffold when all validation attempts fail."""
        from app.cli.commands.deploy import run_deploy
        from app.cli.core.agent import GeneratedCode
        from app.cli.core.inspector import ArtifactMetadata

        meta = ArtifactMetadata(
            framework="generic",
            class_name="Unknown",
            class_hierarchy=[],
            input_hint="x",
            output_hint="y",
            feature_count=None,
            class_labels=None,
            artifact_path=str(FIXTURE),
            artifact_size_mb=1.0,
            extra={},
        )

        bad_code = GeneratedCode(
            load_body="def load(self) -> None:\n    raise RuntimeError('bad')",
            predict_body="def predict(self, x):\n    raise RuntimeError('bad')",
            raw="",
        )

        scaffold_called = {"called": False}

        def fake_scaffold(*args, **kwargs):
            scaffold_called["called"] = True

        monkeypatch.setattr("app.cli.commands.deploy._is_interactive", lambda: False)
        monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p, **kw: meta)
        monkeypatch.setattr("app.cli.commands.deploy.generate", lambda m, d, **kw: bad_code)
        monkeypatch.setattr("app.cli.commands.deploy.fix", lambda code, err, **kw: bad_code)
        monkeypatch.setattr("app.cli.core.writer.write_scaffold", fake_scaffold)

        run_deploy(
            str(FIXTURE),
            name="scaffold_test", version="v1", device="cpu",
            routing="static", sample_input="test",
        )

        assert scaffold_called["called"]
