"""CLI Phase 4 — validator.py tests: validation loop for generated load() and predict()."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.cli.inspector import ArtifactMetadata
from app.cli.validator import ValidationResult, build_definition_source, validate_pipeline

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _make_meta(**kwargs) -> ArtifactMetadata:
    defaults = dict(
        framework="sklearn",
        class_name="Pipeline",
        class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
        input_hint="raw text string",
        output_hint="integer class label (classes: [0, 1])",
        feature_count=None,
        class_labels=[0, 1],
        artifact_path=str(FIXTURE),
        artifact_size_mb=1.5,
    )
    defaults.update(kwargs)
    return ArtifactMetadata(**defaults)


# ---------------------------------------------------------------------------
# build_definition_source
# ---------------------------------------------------------------------------

def test_build_definition_source_contains_model_name_and_version():
    meta = _make_meta()
    src = build_definition_source(meta, "sentiment", "v1", "def load(self) -> None:\n    pass", "def predict(self, x):\n    return x")
    assert "MODEL_NAME = 'sentiment'" in src
    assert "MODEL_VERSION = 'v1'" in src


def test_build_definition_source_contains_method_bodies():
    meta = _make_meta()
    load = "def load(self) -> None:\n    self._model = 'loaded'"
    predict = "def predict(self, x):\n    return self._model"
    src = build_definition_source(meta, "m", "v1", load, predict)
    assert "def load(self)" in src
    assert "def predict(self, x)" in src
    assert "build_pipeline" in src


# ---------------------------------------------------------------------------
# validate_pipeline — success path
# ---------------------------------------------------------------------------

_GOOD_LOAD = "def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{path}')"
_GOOD_PREDICT = "def predict(self, x):\n    return int(self._model.predict([x])[0])"


def test_validate_pipeline_success():
    meta = _make_meta()
    load = _GOOD_LOAD.format(path=str(FIXTURE))
    src = build_definition_source(meta, "sentiment", "v1", load, _GOOD_PREDICT)
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_pipeline(src, "this movie was great", Path(tmp))
    assert result.success is True
    assert result.output in (0, 1)
    assert result.error is None


# ---------------------------------------------------------------------------
# validate_pipeline — failure path
# ---------------------------------------------------------------------------

def test_validate_pipeline_bad_load_returns_error():
    meta = _make_meta()
    bad_load = "def load(self) -> None:\n    raise RuntimeError('intentional failure')"
    src = build_definition_source(meta, "sentiment", "v1", bad_load, _GOOD_PREDICT)
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_pipeline(src, "test", Path(tmp))
    assert result.success is False
    assert "intentional failure" in result.error


def test_validate_pipeline_bad_predict_returns_error():
    meta = _make_meta()
    load = _GOOD_LOAD.format(path=str(FIXTURE))
    bad_predict = "def predict(self, x):\n    raise ValueError('bad predict')"
    src = build_definition_source(meta, "sentiment", "v1", load, bad_predict)
    with tempfile.TemporaryDirectory() as tmp:
        result = validate_pipeline(src, "test", Path(tmp))
    assert result.success is False
    assert "bad predict" in result.error


def test_validate_pipeline_no_files_written_on_failure(tmp_path):
    meta = _make_meta()
    bad_load = "def load(self) -> None:\n    raise RuntimeError('fail')"
    src = build_definition_source(meta, "sentiment", "v1", bad_load, _GOOD_PREDICT)
    validate_pipeline(src, "test", tmp_path)
    # definition.py is written to tmp dir for import, but no model files
    assert not (tmp_path / "models").exists()


# ---------------------------------------------------------------------------
# deploy retry loop (integration via mocked agent)
# ---------------------------------------------------------------------------

def test_deploy_retries_on_validation_failure_and_succeeds(monkeypatch, tmp_path):
    """First generation fails validation; second (fix) succeeds."""
    from app.cli.deploy import _run_validation_loop
    from app.cli.prompts import DeployAnswers
    from app.cli.agent import GeneratedCode

    meta = _make_meta()
    answers = DeployAnswers(
        name="sentiment", version="v1", device="cpu",
        routing="static", sample_input="this movie was great",
    )

    bad_load = "def load(self) -> None:\n    raise RuntimeError('first attempt fails')"
    good_load = _GOOD_LOAD.format(path=str(FIXTURE))

    bad_code = GeneratedCode(load_body=bad_load, predict_body=_GOOD_PREDICT, raw=bad_load + "\n" + _GOOD_PREDICT)
    good_code = GeneratedCode(load_body=good_load, predict_body=_GOOD_PREDICT, raw=good_load + "\n" + _GOOD_PREDICT)

    monkeypatch.setattr("app.cli.deploy.fix", lambda raw, error, **kw: good_code)

    result = _run_validation_loop(meta, answers, "models/sentiment/v1/sentiment.pkl", bad_code)
    assert result is not None
    assert result.load_body == good_load


def test_deploy_exits_after_max_retries(monkeypatch):
    """All 3 attempts fail — returns None without writing files."""
    from app.cli.deploy import _run_validation_loop
    from app.cli.prompts import DeployAnswers
    from app.cli.agent import GeneratedCode

    meta = _make_meta()
    answers = DeployAnswers(
        name="sentiment", version="v1", device="cpu",
        routing="static", sample_input="test",
    )

    bad_load = "def load(self) -> None:\n    raise RuntimeError('always fails')"
    bad_code = GeneratedCode(load_body=bad_load, predict_body=_GOOD_PREDICT, raw="")

    monkeypatch.setattr("app.cli.deploy.fix", lambda raw, error, **kw: bad_code)

    result = _run_validation_loop(meta, answers, "models/sentiment/v1/sentiment.pkl", bad_code)
    assert result is None
