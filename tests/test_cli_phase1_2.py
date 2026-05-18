"""Phase 1 + Phase 2 CLI tests — inspector, prompts, and deploy command."""
import subprocess
import sys
from pathlib import Path

import pytest

VENV_PYTHON = Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"
ROOT = Path(__file__).parent.parent


def _venv_python():
    """Return the venv python path if it exists, else fall back to sys.executable."""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


# ---------------------------------------------------------------------------
# Phase 1 — inspector unit tests
# ---------------------------------------------------------------------------

def test_inspect_sklearn_fixture():
    from app.cli.core.inspector import inspect_artifact
    meta = inspect_artifact(str(FIXTURE))
    assert meta.framework == "sklearn"
    assert meta.class_name == "Pipeline"
    assert "TfidfVectorizer" in meta.class_hierarchy
    assert "LogisticRegression" in meta.class_hierarchy
    assert meta.input_hint == "raw text string"
    assert meta.class_labels is not None
    assert meta.artifact_size_mb >= 0


def test_inspect_missing_file():
    from app.cli.core.inspector import inspect_artifact
    with pytest.raises(FileNotFoundError):
        inspect_artifact("nonexistent.pkl")


def test_inspect_invalid_file(tmp_path):
    import warnings
    from app.cli.core.inspector import inspect_artifact
    bad = tmp_path / "bad.pkl"
    bad.write_bytes(b"not a pickle")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        meta = inspect_artifact(str(bad))
    assert meta.framework == "unknown"
    assert "inspection_warning" in meta.extra
    assert len(w) == 1 and "partial metadata" in str(w[0].message)


# ---------------------------------------------------------------------------
# Phase 1 — CLI integration tests (subprocess)
# ---------------------------------------------------------------------------

def test_cli_deploy_prints_metadata():
    # Pass all flags so non-interactive mode doesn't exit early.
    result = subprocess.run(
        [
            _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
            "--name", "sentiment",
            "--version", "v1",
            "--device", "cpu",
            "--routing", "static",
            "--sample-input", "great movie",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "sklearn" in result.stdout
    assert "TfidfVectorizer" in result.stdout
    assert "raw text string" in result.stdout


def test_cli_deploy_aborts_on_no():
    # Non-interactive mode with no flags exits 1 with a "Missing" message.
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", str(FIXTURE)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 1
    assert "Missing" in result.stdout


def test_cli_deploy_missing_artifact():
    result = subprocess.run(
        [_venv_python(), "-m", "app.cli", "deploy", "no_such_file.pkl"],
        input="y\n",
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Phase 2 — prompts unit tests
# ---------------------------------------------------------------------------

def test_derive_name():
    from app.cli.core.prompts import _derive_name
    assert _derive_name("sentiment.pkl") == "sentiment"
    assert _derive_name("my_model.joblib") == "my"
    assert _derive_name("iris_classifier.pkl") == "iris"
    assert _derive_name("fraud_pipeline.pkl") == "fraud"


def test_next_version_no_existing(tmp_path):
    from app.cli.core.prompts import _next_version
    assert _next_version("newmodel", models_root=str(tmp_path)) == "v1"


def test_next_version_increments(tmp_path):
    from app.cli.core.prompts import _next_version
    (tmp_path / "mymodel" / "v1").mkdir(parents=True)
    (tmp_path / "mymodel" / "v2").mkdir(parents=True)
    assert _next_version("mymodel", models_root=str(tmp_path)) == "v3"


def test_next_version_ignores_non_version_dirs(tmp_path):
    from app.cli.core.prompts import _next_version
    (tmp_path / "mymodel" / "v1").mkdir(parents=True)
    (tmp_path / "mymodel" / "staging").mkdir(parents=True)
    assert _next_version("mymodel", models_root=str(tmp_path)) == "v2"


def test_collect_answers_all_flags(tmp_path):
    """When all flags provided, no prompts are shown and answers are returned."""
    from app.cli.core.prompts import collect_answers
    answers = collect_answers(
        "sentiment.pkl",
        name="sentiment",
        version="v1",
        device="cpu",
        routing="static",
        sample_input="great movie",
        models_root=str(tmp_path),
    )
    assert answers.name == "sentiment"
    assert answers.version == "v1"
    assert answers.device == "cpu"
    assert answers.routing == "static"
    assert answers.sample_input == "great movie"


def test_collect_answers_non_tty_missing_flags(tmp_path, monkeypatch):
    """Non-interactive mode with missing flags should exit with code 1."""
    from app.cli.core import prompts
    monkeypatch.setattr(prompts, "_is_interactive", lambda: False)
    with pytest.raises(SystemExit) as exc:
        prompts.collect_answers(
            "sentiment.pkl",
            name="sentiment",
            # version, device, routing, sample_input all missing
            models_root=str(tmp_path),
        )
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Phase 2 — CLI integration: all-flags path (non-interactive, no prompts)
# ---------------------------------------------------------------------------

def test_cli_deploy_all_flags_shows_preview():
    """Passing all flags skips prompts and shows the preview table."""
    result = subprocess.run(
        [
            _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
            "--name", "sentiment",
            "--version", "v1",
            "--device", "cpu",
            "--routing", "static",
            "--sample-input", "this movie was great",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0
    assert "Preview" in result.stdout
    assert "models/sentiment/v1/definition.py" in result.stdout
    assert "sentiment.pkl" in result.stdout
    assert "app/config/routing.py" in result.stdout


def test_cli_deploy_non_interactive_missing_flags_exits():
    """Non-interactive mode with missing flags must exit non-zero."""
    result = subprocess.run(
        [
            _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
            "--name", "sentiment",
            # version, device, routing, sample-input missing
        ],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 1
    assert "Missing" in result.stdout or "Missing" in result.stderr
