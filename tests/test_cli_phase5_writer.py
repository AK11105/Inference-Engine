"""CLI Phase 5 — writer.py tests: file writes and routing patch."""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from app.cli.inspector import ArtifactMetadata
from app.cli.prompts import DeployAnswers
from app.cli.writer import _patch_routing, write_deployment

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"

_ROUTING_TEMPLATE = """\
ROUTES = {
    "echo": {
        "strategy": "canary",
        "primary": "v1",
        "canary": "v2",
        "canary_percent": 50,
    },
}
"""

_GOOD_LOAD = "def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{path}')"
_GOOD_PREDICT = "def predict(self, x):\n    return int(self._model.predict([x])[0])"


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


def _make_answers(**kwargs) -> DeployAnswers:
    defaults = dict(
        name="sentiment", version="v1", device="cpu",
        routing="static", sample_input="this movie was great",
    )
    defaults.update(kwargs)
    return DeployAnswers(**defaults)


# ---------------------------------------------------------------------------
# _patch_routing
# ---------------------------------------------------------------------------

def test_patch_routing_appends_new_model(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    _patch_routing(routing, "sentiment", "v1", "static")
    src = routing.read_text()
    ast.parse(src)  # must be valid Python
    assert '"sentiment"' in src
    assert '"static"' in src
    assert '"v1"' in src


def test_patch_routing_all_strategies(tmp_path):
    for strategy in ("static", "canary", "ab"):
        routing = tmp_path / f"routing_{strategy}.py"
        routing.write_text(_ROUTING_TEMPLATE)
        _patch_routing(routing, f"model_{strategy}", "v1", strategy)
        src = routing.read_text()
        ast.parse(src)
        assert f'"model_{strategy}"' in src
        assert f'"{strategy}"' in src


def test_patch_routing_idempotent_no_duplicate(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    _patch_routing(routing, "sentiment", "v1", "static")
    _patch_routing(routing, "sentiment", "v2", "static")  # re-run with new version
    src = routing.read_text()
    ast.parse(src)
    # Only one entry for "sentiment"
    assert src.count('"sentiment"') == 1
    assert '"v2"' in src


def test_patch_routing_preserves_existing_entries(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    _patch_routing(routing, "new_model", "v1", "static")
    src = routing.read_text()
    ast.parse(src)
    assert '"echo"' in src
    assert '"new_model"' in src


# ---------------------------------------------------------------------------
# write_deployment
# ---------------------------------------------------------------------------

def test_write_deployment_creates_directory_structure(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(artifact_path=str(FIXTURE))
    answers = _make_answers()
    load = _GOOD_LOAD.format(path=str(FIXTURE))

    write_deployment(
        meta, answers, str(FIXTURE),
        load_body=load, predict_body=_GOOD_PREDICT,
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    dest = tmp_path / "models" / "sentiment" / "v1"
    assert dest.is_dir()
    assert (dest / "definition.py").exists()
    assert (dest / "sentiment.pkl").exists()


def test_write_deployment_definition_contains_name_and_version(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(artifact_path=str(FIXTURE))
    answers = _make_answers()
    load = _GOOD_LOAD.format(path=str(FIXTURE))

    write_deployment(
        meta, answers, str(FIXTURE),
        load_body=load, predict_body=_GOOD_PREDICT,
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "sentiment" / "v1" / "definition.py").read_text()
    assert "MODEL_NAME = 'sentiment'" in src
    assert "MODEL_VERSION = 'v1'" in src


def test_write_deployment_patches_routing(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(artifact_path=str(FIXTURE))
    answers = _make_answers()
    load = _GOOD_LOAD.format(path=str(FIXTURE))

    write_deployment(
        meta, answers, str(FIXTURE),
        load_body=load, predict_body=_GOOD_PREDICT,
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = routing.read_text()
    ast.parse(src)
    assert '"sentiment"' in src


def test_write_deployment_artifact_is_copied(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(artifact_path=str(FIXTURE))
    answers = _make_answers()
    load = _GOOD_LOAD.format(path=str(FIXTURE))

    write_deployment(
        meta, answers, str(FIXTURE),
        load_body=load, predict_body=_GOOD_PREDICT,
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    dest_pkl = tmp_path / "models" / "sentiment" / "v1" / "sentiment.pkl"
    assert dest_pkl.exists()
    assert dest_pkl.stat().st_size == FIXTURE.stat().st_size


def test_write_deployment_idempotent_overwrite(tmp_path):
    """Re-running with same name/version overwrites without duplicating routing entry."""
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(artifact_path=str(FIXTURE))
    answers = _make_answers()
    load = _GOOD_LOAD.format(path=str(FIXTURE))

    for _ in range(2):
        write_deployment(
            meta, answers, str(FIXTURE),
            load_body=load, predict_body=_GOOD_PREDICT,
            models_root=str(tmp_path / "models"),
            routing_path=routing,
        )

    src = routing.read_text()
    ast.parse(src)
    assert src.count('"sentiment"') == 1
