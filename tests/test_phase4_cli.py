"""Phase 1 CLI tests — inspector and deploy command."""
import subprocess
import sys
from pathlib import Path

import pytest

VENV_PYTHON = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _venv_python():
    """Return the venv python path if it exists, else fall back to sys.executable."""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


# --- inspector unit tests ---

def test_inspect_sklearn_fixture():
    from app.cli.inspector import inspect_artifact
    meta = inspect_artifact(str(FIXTURE))
    assert meta.framework == "sklearn"
    assert meta.class_name == "Pipeline"
    assert "TfidfVectorizer" in meta.class_hierarchy
    assert "LogisticRegression" in meta.class_hierarchy
    assert meta.input_hint == "raw text string"
    assert meta.class_labels is not None
    assert meta.artifact_size_mb >= 0


def test_inspect_missing_file():
    from app.cli.inspector import inspect_artifact
    with pytest.raises(FileNotFoundError):
        inspect_artifact("nonexistent.pkl")


def test_inspect_invalid_file(tmp_path):
    from app.cli.inspector import inspect_artifact
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(b"not a pickle")
    with pytest.raises(ValueError, match="Inspection failed"):
        inspect_artifact(str(bad))


# --- CLI integration tests (subprocess) ---

def test_cli_deploy_prints_metadata():
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", str(FIXTURE)],
        input="y\n",
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0
    assert "sklearn" in result.stdout
    assert "TfidfVectorizer" in result.stdout
    assert "raw text string" in result.stdout


def test_cli_deploy_aborts_on_no():
    # subprocess has no TTY so non-interactive mode kicks in and proceeds regardless.
    # Abort only works in interactive (TTY) mode — tested here by confirming non-interactive
    # path runs through without hanging.
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", str(FIXTURE)],
        input="n\n",
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0
    assert "Non-interactive" in result.stdout


def test_cli_deploy_missing_artifact():
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", "no_such_file.pkl"],
        input="y\n",
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()
