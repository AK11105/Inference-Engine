"""CLI Phase 6 — fix.py tests."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cli.core.agent import GeneratedCode
from app.cli.commands.fix import _splice_methods, run_fix
from app.cli.core.validator import build_definition_source

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"

_GOOD_LOAD = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
_GOOD_PREDICT = "def predict(self, x):\n    return int(self._model.predict([x])[0])"
_BAD_LOAD = "def load(self) -> None:\n    raise RuntimeError('broken')"


def _make_source(load=_GOOD_LOAD, predict=_GOOD_PREDICT) -> str:
    from app.cli.core.inspector import ArtifactMetadata
    meta = ArtifactMetadata(
        framework="sklearn", class_name="Pipeline",
        class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
        input_hint="raw text string", output_hint="integer class label",
        feature_count=None, class_labels=[0, 1],
        artifact_path=str(FIXTURE), artifact_size_mb=1.5,
    )
    return build_definition_source(meta, "sentiment", "v1", load, predict)


# ---------------------------------------------------------------------------
# _splice_methods
# ---------------------------------------------------------------------------

def test_splice_methods_replaces_load_and_predict():
    original = _make_source()
    new_load = "def load(self) -> None:\n    self._model = 'replaced'"
    new_predict = "def predict(self, x):\n    return 42"
    result = _splice_methods(original, new_load, new_predict)
    assert "replaced" in result
    assert "return 42" in result
    assert "broken" not in result


def test_splice_methods_preserves_surrounding_code():
    original = _make_source()
    result = _splice_methods(original, _GOOD_LOAD, _GOOD_PREDICT)
    assert "MODEL_NAME" in result
    assert "build_pipeline" in result


# ---------------------------------------------------------------------------
# run_fix — valid pipeline exits cleanly
# ---------------------------------------------------------------------------

def test_run_fix_valid_pipeline_exits_cleanly(tmp_path, monkeypatch):
    definition = tmp_path / "definition.py"
    definition.write_text(_make_source())

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: False)
    # Non-interactive with a valid pipeline should print "Nothing to fix" and return
    # We need to supply sample_input — patch validate_pipeline to succeed immediately
    from app.cli.commands import fix as fix_mod
    monkeypatch.setattr(
        fix_mod, "validate_pipeline",
        lambda src, inp, tmp: type("R", (), {"success": True, "output": 1, "error": None})(),
    )

    # Patch input() for sample_input since _is_interactive returns False → sys.exit(1)
    # Instead make it interactive and supply input
    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "this movie was great")

    run_fix(str(tmp_path))  # should return without raising


# ---------------------------------------------------------------------------
# run_fix — broken pipeline, fix succeeds on first retry
# ---------------------------------------------------------------------------

def test_run_fix_broken_then_fixed(tmp_path, monkeypatch):
    definition = tmp_path / "definition.py"
    definition.write_text(_make_source(load=_BAD_LOAD))

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: True)
    inputs = iter(["this movie was great", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    good_code = GeneratedCode(load_body=_GOOD_LOAD, predict_body=_GOOD_PREDICT, raw="")

    call_count = {"n": 0}

    def fake_validate(src, inp, tmp):
        call_count["n"] += 1
        # First call (original) fails; second call (after fix) succeeds
        if call_count["n"] == 1:
            return type("R", (), {"success": False, "output": None, "error": "RuntimeError: broken"})()
        return type("R", (), {"success": True, "output": 1, "error": None})()

    monkeypatch.setattr("app.cli.commands.fix.validate_pipeline", fake_validate)
    monkeypatch.setattr("app.cli.commands.fix.llm_fix", lambda src, err, **kw: good_code)

    run_fix(str(tmp_path))

    written = definition.read_text()
    assert "broken" not in written


# ---------------------------------------------------------------------------
# run_fix — all retries fail, no file written
# ---------------------------------------------------------------------------

def test_run_fix_all_retries_fail_no_write(tmp_path, monkeypatch):
    original = _make_source(load=_BAD_LOAD)
    definition = tmp_path / "definition.py"
    definition.write_text(original)

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "test input")

    bad_code = GeneratedCode(load_body=_BAD_LOAD, predict_body=_GOOD_PREDICT, raw="")
    monkeypatch.setattr(
        "app.cli.commands.fix.validate_pipeline",
        lambda src, inp, tmp: type("R", (), {"success": False, "output": None, "error": "still broken"})(),
    )
    monkeypatch.setattr("app.cli.commands.fix.llm_fix", lambda src, err, **kw: bad_code)

    with pytest.raises(SystemExit) as exc:
        run_fix(str(tmp_path))

    assert exc.value.code == 1
    # File must be unchanged
    assert definition.read_text() == original


# ---------------------------------------------------------------------------
# run_fix — missing definition.py
# ---------------------------------------------------------------------------

def test_run_fix_missing_definition(tmp_path):
    with pytest.raises(SystemExit) as exc:
        run_fix(str(tmp_path))
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# __main__ — fix subcommand registered
# ---------------------------------------------------------------------------

def test_main_fix_subcommand_registered():
    import argparse
    from app.cli.__main__ import main
    import sys
    with patch.object(sys, "argv", ["inference-engine", "fix", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0


def test_splice_methods_result_is_valid_python():
    """Regression: result must parse without SyntaxError / IndentationError."""
    import ast
    original = _make_source()
    new_load = "def load(self) -> None:\n    self._model = 'x'"
    new_predict = "def predict(self, x):\n    return 1"
    result = _splice_methods(original, new_load, new_predict)
    ast.parse(result)  # must not raise


def test_splice_methods_no_blank_line_between_methods():
    """Regression: splice must work even when methods have no blank line between them."""
    import ast
    import re
    original = _make_source()
    # Collapse the blank line that sits between load-body and predict def
    no_blank_source = re.sub(r"\n\n(    def predict)", r"\n\1", original)
    ast.parse(no_blank_source)  # guard: must be valid before we test

    new_load = "def load(self) -> None:\n    self._model = 'no_blank'"
    new_predict = "def predict(self, x):\n    return 99"
    result = _splice_methods(no_blank_source, new_load, new_predict)
    ast.parse(result)
    assert "no_blank" in result
    assert "return 99" in result


def test_splice_methods_with_helper_method():
    """Regression: helper methods inside the class must not truncate load."""
    import ast
    import textwrap
    source_with_helper = textwrap.dedent("""\
        from app.domain.models.base import BaseModel
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.pipelines.base import InferencePipeline

        MODEL_NAME = 'sentiment'
        MODEL_VERSION = 'v1'

        class _GeneratedModel(BaseModel):
            def load(self) -> None:
                self._model = None

            def _helper(self):
                return 42

            def predict(self, x):
                return self._helper()

        def build_pipeline() -> InferencePipeline:
            model = _GeneratedModel()
            model.load()
            return InferencePipeline(
                preprocessor=IdentityPreprocessor(),
                model=model,
                postprocessor=IdentityPostprocessor(),
            )
    """)
    new_load = "def load(self) -> None:\n    self._model = 'helper_test'"
    new_predict = "def predict(self, x):\n    return 7"
    result = _splice_methods(source_with_helper, new_load, new_predict)
    ast.parse(result)
    assert "helper_test" in result
    assert "return 7" in result
    assert "_helper" in result  # untouched


# ---------------------------------------------------------------------------
# run_fix — non-interactive mode with --sample-input flag
# ---------------------------------------------------------------------------

def test_run_fix_non_interactive_with_sample_input_flag(tmp_path, monkeypatch):
    """Non-interactive + --sample-input provided → should not exit, runs normally."""
    definition = tmp_path / "definition.py"
    definition.write_text(_make_source())

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: False)
    from app.cli.commands import fix as fix_mod
    monkeypatch.setattr(
        fix_mod, "validate_pipeline",
        lambda src, inp, tmp: type("R", (), {"success": True, "output": 1, "error": None})(),
    )

    run_fix(str(tmp_path), sample_input="this movie was great")  # must not raise


def test_run_fix_non_interactive_without_sample_input_exits(tmp_path, monkeypatch):
    """Non-interactive + no --sample-input → exits with code 1."""
    definition = tmp_path / "definition.py"
    definition.write_text(_make_source())

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: False)

    with pytest.raises(SystemExit) as exc:
        run_fix(str(tmp_path), sample_input=None)

    assert exc.value.code == 1


def test_run_fix_interactive_prompts_when_no_flag(tmp_path, monkeypatch):
    """Interactive + no flag → falls back to input() prompt."""
    definition = tmp_path / "definition.py"
    definition.write_text(_make_source())

    monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: True)
    prompted = {"called": False}

    def fake_input(_):
        prompted["called"] = True
        return "this movie was great"

    monkeypatch.setattr("builtins.input", fake_input)
    from app.cli.commands import fix as fix_mod
    monkeypatch.setattr(
        fix_mod, "validate_pipeline",
        lambda src, inp, tmp: type("R", (), {"success": True, "output": 1, "error": None})(),
    )

    run_fix(str(tmp_path), sample_input=None)
    assert prompted["called"]


def test_main_fix_subcommand_has_sample_input_flag():
    """--sample-input must be a registered argument on the fix subparser."""
    import sys
    from app.cli.__main__ import main
    from unittest.mock import patch

    with patch.object(sys, "argv", ["inference-engine", "fix", "some/dir", "--sample-input", "hello"]):
        with patch("app.cli.commands.fix.run_fix") as mock_run_fix:
            main()
            mock_run_fix.assert_called_once_with(model_dir="some/dir", sample_input="hello", yes=False)
