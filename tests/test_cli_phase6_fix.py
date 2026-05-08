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
