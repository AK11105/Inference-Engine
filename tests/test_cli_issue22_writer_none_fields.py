"""Issue #22 — write_scaffold must not crash or emit 'None' when
ArtifactMetadata fields (framework, class_name, input_hint, output_hint)
are None after a partial inspection failure.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.core.inspector import ArtifactMetadata
from app.cli.core.prompts import DeployAnswers
from app.cli.core.writer import write_scaffold

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"

_ROUTING_TEMPLATE = """\
ROUTES = {
    "echo": {
        "strategy": "static",
        "primary": "v1",
    },
}
"""


def _make_meta(**kwargs) -> ArtifactMetadata:
    defaults = dict(
        framework=None,
        class_name=None,
        class_hierarchy=[],
        input_hint=None,
        output_hint=None,
        feature_count=None,
        class_labels=None,
        artifact_path=str(FIXTURE),
        artifact_size_mb=0.1,
    )
    defaults.update(kwargs)
    return ArtifactMetadata(**defaults)


def _make_answers(**kwargs) -> DeployAnswers:
    defaults = dict(
        name="mymodel", version="v1", device="cpu",
        routing="static", sample_input="input",
    )
    defaults.update(kwargs)
    return DeployAnswers(**defaults)


# ---------------------------------------------------------------------------
# Core bug: all None fields → no crash, "unknown" substituted
# ---------------------------------------------------------------------------

def test_write_scaffold_all_none_fields_does_not_crash(tmp_path):
    """write_scaffold must not raise KeyError or any exception when all
    nullable fields are None (the exact scenario from issue #22)."""
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta()
    answers = _make_answers()

    # Must not raise
    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )


def test_write_scaffold_none_fields_replaced_with_unknown(tmp_path):
    """None fields must appear as 'unknown' in the written scaffold, not 'None'."""
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta()
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    # Check that the comment lines don't contain literal 'None'
    comment_lines = [l for l in src.splitlines() if l.startswith("#")]
    assert all("None" not in l for l in comment_lines)
    assert any("unknown" in l for l in comment_lines)


def test_write_scaffold_none_framework_replaced(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(framework=None)
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    assert "Framework detected: unknown" in src
    assert "Framework detected: None" not in src


def test_write_scaffold_none_class_name_replaced(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(class_name=None)
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    assert "Class: unknown" in src
    assert "Class: None" not in src


def test_write_scaffold_none_input_hint_replaced(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(input_hint=None)
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    assert "Input hint: unknown" in src
    assert "Input hint: None" not in src


def test_write_scaffold_none_output_hint_replaced(tmp_path):
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(output_hint=None)
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    assert "Output hint: unknown" in src
    assert "Output hint: None" not in src


def test_write_scaffold_known_fields_preserved(tmp_path):
    """Fields that are set must not be replaced with 'unknown'."""
    routing = tmp_path / "routing.py"
    routing.write_text(_ROUTING_TEMPLATE)
    meta = _make_meta(framework="sklearn", class_name="Pipeline",
                      input_hint="raw text", output_hint="int label")
    answers = _make_answers()

    write_scaffold(
        meta, answers, str(FIXTURE),
        models_root=str(tmp_path / "models"),
        routing_path=routing,
    )

    src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
    assert "Framework detected: sklearn" in src
    assert "Class: Pipeline" in src
    assert "Input hint: raw text" in src
    assert "Output hint: int label" in src
