"""CLI Phase 7 — polish tests: --dry-run, error messages, env vars."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _venv_python() -> str:
    for candidate in (
        ROOT / ".venv" / "Scripts" / "python.exe",  # Windows
        ROOT / ".venv" / "bin" / "python",           # Linux/macOS
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


# ---------------------------------------------------------------------------
# --dry-run: no files written, exits 0
# ---------------------------------------------------------------------------

def test_dry_run_writes_nothing(monkeypatch):
    """--dry-run runs validation but never calls write_deployment."""
    from app.cli.commands.deploy import run_deploy
    from app.cli.core.agent import GeneratedCode

    good_load = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
    good_predict = "def predict(self, x):\n    return int(self._model.predict([x])[0])"
    good_code = GeneratedCode(load_body=good_load, predict_body=good_predict, raw="")

    monkeypatch.setattr("app.cli.commands.deploy._is_interactive", lambda: False)
    monkeypatch.setattr("app.cli.commands.deploy.generate", lambda meta, dest, **kw: good_code)

    write_called = {"called": False}

    def fake_write(*args, **kwargs):
        write_called["called"] = True

    monkeypatch.setattr("app.cli.core.writer.write_deployment", fake_write)

    run_deploy(
        str(FIXTURE),
        name="sentiment", version="v1", device="cpu",
        routing="static", sample_input="this movie was great",
        dry_run=True,
    )

    assert not write_called["called"]


def test_dry_run_flag_via_subprocess():
    """--dry-run flag is accepted and exits 0 (no LLM needed — mocked via env)."""
    result = subprocess.run(
        [
            _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
            "--name", "sentiment", "--version", "v99",
            "--device", "cpu", "--routing", "static",
            "--sample-input", "great movie",
            "--dry-run",
        ],
        capture_output=True, text=True, cwd=str(ROOT),
        env={**__import__("os").environ, "GROQ_API_KEY": ""},
    )
    # Will fail at LLM step (no key), but the flag must be accepted (not argparse error)
    assert "unrecognized" not in result.stdout
    assert "unrecognized" not in result.stderr


# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------

def test_missing_artifact_error_message():
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", "no_such_file.pkl",
         "--name", "x", "--version", "v1", "--device", "cpu",
         "--routing", "static", "--sample-input", "test"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_pytorch_framework_error_message(monkeypatch):
    """Phase 8: PyTorch is no longer rejected — it proceeds to LLM generation.
    Without a GROQ key the deploy exits, but NOT with the old 'not supported' message.
    """
    from app.cli.commands.deploy import run_deploy
    from app.cli.core.inspector import ArtifactMetadata
    from app.cli.core.agent import GeneratedCode

    pytorch_meta = ArtifactMetadata(
        framework="pytorch", class_name="MyNet",
        class_hierarchy=[], input_hint="tensor", output_hint="tensor",
        feature_count=None, class_labels=None,
        artifact_path=str(FIXTURE), artifact_size_mb=1.0,
        extra={},
    )
    monkeypatch.setattr("app.cli.commands.deploy._is_interactive", lambda: False)
    monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p: pytorch_meta)

    # Simulate LLM generating code that always fails validation → scaffold fallback
    bad_code = GeneratedCode(
        load_body="def load(self) -> None:\n    raise RuntimeError('bad')",
        predict_body="def predict(self, x):\n    raise RuntimeError('bad')",
        raw="",
    )
    monkeypatch.setattr("app.cli.commands.deploy.generate", lambda m, d, **kw: bad_code)
    monkeypatch.setattr("app.cli.commands.deploy.fix", lambda code, err, **kw: bad_code)

    scaffold_called = {"called": False}
    def fake_scaffold(*args, **kwargs):
        scaffold_called["called"] = True
    monkeypatch.setattr("app.cli.core.writer.write_scaffold", fake_scaffold)

    # Should NOT raise SystemExit — falls back to scaffold
    run_deploy(
        str(FIXTURE),
        name="pytorch_test", version="v1", device="cpu",
        routing="static", sample_input="test",
    )
    assert scaffold_called["called"]


def test_missing_groq_key_error_message(monkeypatch):
    """Missing GROQ_API_KEY produces a clear error, not a traceback."""
    import os
    from app.cli.commands.deploy import run_deploy
    from app.cli.core.inspector import ArtifactMetadata

    meta = ArtifactMetadata(
        framework="sklearn", class_name="Pipeline",
        class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
        input_hint="raw text string", output_hint="integer class label",
        feature_count=None, class_labels=[0, 1],
        artifact_path=str(FIXTURE), artifact_size_mb=1.5,
    )
    monkeypatch.setattr("app.cli.commands.deploy._is_interactive", lambda: False)
    monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p: meta)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        run_deploy(
            str(FIXTURE),
            name="sentiment", version="v1", device="cpu",
            routing="static", sample_input="test",
        )


# ---------------------------------------------------------------------------
# --dry-run flag registered in __main__
# ---------------------------------------------------------------------------

def test_dry_run_flag_registered():
    from app.cli.__main__ import main
    with patch.object(sys, "argv", ["inference-engine", "deploy", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
    assert exc.value.code == 0
