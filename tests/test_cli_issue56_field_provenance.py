"""Issue #56 — FieldValue provenance for ArtifactMetadata interpreted fields.

TDD red-phase tests: these define the expected behavior of the FieldValue
dataclass and the updated ArtifactMetadata interface. All tests should FAIL
before implementation and PASS after.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


# ===========================================================================
# Part 1: FieldValue dataclass behavior
# ===========================================================================

class TestFieldValueCreation:
    """FieldValue can be instantiated with value, source, and confidence."""

    def test_basic_creation(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert fv.value == "sklearn"
        assert fv.source == "extractor"
        assert fv.confidence == "high"

    def test_all_valid_sources(self):
        from app.cli.core.inspector import FieldValue

        for source in ("filesystem", "extractor", "llm", "user", "default"):
            fv = FieldValue(value="x", source=source, confidence="medium")
            assert fv.source == source

    def test_all_valid_confidences(self):
        from app.cli.core.inspector import FieldValue

        for conf in ("high", "medium", "low"):
            fv = FieldValue(value="x", source="extractor", confidence=conf)
            assert fv.confidence == conf

    def test_value_can_be_any_type(self):
        from app.cli.core.inspector import FieldValue

        fv_str = FieldValue(value="sklearn", source="extractor", confidence="high")
        fv_list = FieldValue(value=["a", "b"], source="user", confidence="high")
        fv_int = FieldValue(value=42, source="default", confidence="low")
        assert fv_str.value == "sklearn"
        assert fv_list.value == ["a", "b"]
        assert fv_int.value == 42


class TestFieldValueEquality:
    """FieldValue supports comparison with plain values via __eq__."""

    def test_eq_with_plain_string(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert fv == "sklearn"
        assert "sklearn" == fv

    def test_eq_with_another_field_value(self):
        from app.cli.core.inspector import FieldValue

        fv1 = FieldValue(value="sklearn", source="extractor", confidence="high")
        fv2 = FieldValue(value="sklearn", source="llm", confidence="medium")
        assert fv1 == fv2  # equality compares .value only

    def test_neq_different_value(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert fv != "pytorch"
        assert fv != FieldValue(value="pytorch", source="extractor", confidence="high")

    def test_eq_with_none(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value=None, source="default", confidence="low")
        assert fv == None  # noqa: E711 — intentional None comparison

    def test_eq_with_non_none_is_not_none(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert fv != None  # noqa: E711


class TestFieldValueStringRepresentation:
    """FieldValue converts to string via __str__ using its .value."""

    def test_str_returns_value(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert str(fv) == "sklearn"

    def test_str_none_value(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value=None, source="default", confidence="low")
        assert str(fv) == "None"

    def test_format_string_interpolation(self):
        """FieldValue works in f-strings and .format() calls."""
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert f"Framework: {fv}" == "Framework: sklearn"
        assert "Framework: {}".format(fv) == "Framework: sklearn"


class TestFieldValueHashability:
    """FieldValue is hashable (can be used in sets/dicts) based on value."""

    def test_hashable(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        # Should not raise
        d = {fv: True}
        assert d[fv] is True

    def test_hash_matches_value_hash(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert hash(fv) == hash("sklearn")


class TestFieldValueSourceHierarchy:
    """Source hierarchy: user > extractor > llm > default.
    A higher-priority source should win when merging."""

    def test_source_priority_ordering(self):
        from app.cli.core.inspector import FieldValue

        # The class must expose a way to compare source priorities
        assert FieldValue.source_priority("user") > FieldValue.source_priority("extractor")
        assert FieldValue.source_priority("extractor") > FieldValue.source_priority("llm")
        assert FieldValue.source_priority("llm") > FieldValue.source_priority("default")
        assert FieldValue.source_priority("filesystem") > FieldValue.source_priority("llm")

    def test_merge_higher_priority_wins(self):
        """When two FieldValues conflict, the one with higher source priority wins."""
        from app.cli.core.inspector import FieldValue

        user_val = FieldValue(value="pytorch", source="user", confidence="high")
        extractor_val = FieldValue(value="sklearn", source="extractor", confidence="high")

        winner = FieldValue.merge(user_val, extractor_val)
        assert winner.value == "pytorch"
        assert winner.source == "user"

    def test_merge_none_vs_value(self):
        """Merging None with a FieldValue returns the FieldValue."""
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        assert FieldValue.merge(None, fv) == fv
        assert FieldValue.merge(fv, None) == fv


# ===========================================================================
# Part 2: Updated ArtifactMetadata interface
# ===========================================================================

class TestArtifactMetadataFieldValueFields:
    """ArtifactMetadata interpreted fields are now FieldValue | None."""

    def _make_meta(self, **kwargs):
        from app.cli.core.inspector import ArtifactMetadata, FieldValue

        defaults = dict(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint=FieldValue(value="raw text string", source="extractor", confidence="high"),
            output_hint=FieldValue(value="integer class label", source="extractor", confidence="high"),
            feature_count=None,
            class_labels=None,
            artifact_path=str(FIXTURE),
            artifact_size_mb=0.1,
            extra={},
            raw_facts={},
            load_format=None,
            inspection_confidence="high",
            interpretation_confidence="high",
            inspection_errors=[],
        )
        defaults.update(kwargs)
        return ArtifactMetadata(**defaults)

    def test_framework_is_field_value(self):
        meta = self._make_meta()
        from app.cli.core.inspector import FieldValue
        assert isinstance(meta.framework, FieldValue)
        assert meta.framework.value == "sklearn"
        assert meta.framework.source == "extractor"

    def test_input_hint_is_field_value(self):
        meta = self._make_meta()
        from app.cli.core.inspector import FieldValue
        assert isinstance(meta.input_hint, FieldValue)
        assert meta.input_hint.value == "raw text string"

    def test_output_hint_is_field_value(self):
        meta = self._make_meta()
        from app.cli.core.inspector import FieldValue
        assert isinstance(meta.output_hint, FieldValue)

    def test_load_format_field_exists(self):
        """load_format is now a top-level FieldValue field, not buried in extra."""
        from app.cli.core.inspector import FieldValue
        meta = self._make_meta(
            load_format=FieldValue(value="state_dict", source="extractor", confidence="high")
        )
        assert meta.load_format.value == "state_dict"
        assert meta.load_format.source == "extractor"

    def test_load_format_can_be_none(self):
        meta = self._make_meta(load_format=None)
        assert meta.load_format is None

    def test_backward_compat_eq(self):
        """Even though framework is FieldValue, comparing with == 'sklearn' works."""
        meta = self._make_meta()
        assert meta.framework == "sklearn"

    def test_backward_compat_str_format(self):
        """FieldValue works in string formatting contexts."""
        meta = self._make_meta()
        result = f"{meta.framework} / {meta.class_name}"
        assert result == "sklearn / Pipeline"


class TestArtifactMetadataConfidenceSplit:
    """The old 'confidence' field is replaced by inspection_confidence
    and interpretation_confidence."""

    def _make_meta(self, **kwargs):
        from app.cli.core.inspector import ArtifactMetadata, FieldValue

        defaults = dict(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            class_name="Pipeline",
            class_hierarchy=[],
            input_hint=FieldValue(value="array-like", source="extractor", confidence="medium"),
            output_hint=FieldValue(value="float", source="extractor", confidence="medium"),
            feature_count=None,
            class_labels=None,
            artifact_path=str(FIXTURE),
            artifact_size_mb=0.1,
            extra={},
            raw_facts={},
            load_format=None,
            inspection_confidence="high",
            interpretation_confidence="medium",
            inspection_errors=[],
        )
        defaults.update(kwargs)
        return ArtifactMetadata(**defaults)

    def test_no_single_confidence_field(self):
        """The old 'confidence' field should not exist anymore."""
        meta = self._make_meta()
        assert not hasattr(meta, "confidence")

    def test_inspection_confidence_exists(self):
        meta = self._make_meta(inspection_confidence="high")
        assert meta.inspection_confidence == "high"

    def test_interpretation_confidence_exists(self):
        meta = self._make_meta(interpretation_confidence="medium")
        assert meta.interpretation_confidence == "medium"

    def test_inspection_confidence_values(self):
        """inspection_confidence accepts high/medium/low."""
        for val in ("high", "medium", "low"):
            meta = self._make_meta(inspection_confidence=val)
            assert meta.inspection_confidence == val

    def test_interpretation_confidence_values(self):
        """interpretation_confidence accepts high/medium/low."""
        for val in ("high", "medium", "low"):
            meta = self._make_meta(interpretation_confidence=val)
            assert meta.interpretation_confidence == val


# ===========================================================================
# Part 3: Inspector produces FieldValue provenance
# ===========================================================================

class TestInspectorProducesFieldValue:
    """inspect_artifact() now returns ArtifactMetadata with FieldValue-wrapped fields."""

    def test_sklearn_framework_has_extractor_source(self):
        from app.cli.core.inspector import FieldValue, inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert isinstance(meta.framework, FieldValue)
        assert meta.framework.value == "sklearn"
        assert meta.framework.source == "extractor"

    def test_sklearn_input_hint_has_extractor_source(self):
        from app.cli.core.inspector import FieldValue, inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert isinstance(meta.input_hint, FieldValue)
        assert meta.input_hint.source == "extractor"

    def test_sklearn_output_hint_has_extractor_source(self):
        from app.cli.core.inspector import FieldValue, inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert isinstance(meta.output_hint, FieldValue)
        assert meta.output_hint.source == "extractor"

    def test_sklearn_framework_confidence_high(self):
        from app.cli.core.inspector import FieldValue, inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert meta.framework.confidence in ("high", "medium")

    def test_inspection_confidence_replaces_old(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert hasattr(meta, "inspection_confidence")
        assert meta.inspection_confidence in ("high", "medium", "low")
        assert not hasattr(meta, "confidence")

    def test_interpretation_confidence_set(self):
        from app.cli.core.inspector import inspect_artifact
        meta = inspect_artifact(str(FIXTURE))
        assert hasattr(meta, "interpretation_confidence")
        assert meta.interpretation_confidence in ("high", "medium", "low")

    def test_unknown_framework_has_low_confidence(self, tmp_path):
        """An unrecognised artifact gets framework with low confidence."""
        from app.cli.core.inspector import FieldValue, inspect_artifact
        p = tmp_path / "mystery.pkl"
        # Write something that'll fail extraction
        import pickle
        with open(p, "wb") as f:
            pickle.dump({"just": "a dict"}, f)
        meta = inspect_artifact(str(p))
        assert meta.framework.confidence == "low" or meta.framework.value == "generic"

    def test_pytorch_load_format_populated(self, tmp_path):
        """PyTorch state_dict files get load_format as a FieldValue."""
        torch = pytest.importorskip("torch")
        from app.cli.core.inspector import FieldValue, inspect_artifact
        sd = {"layer.weight": torch.zeros(4, 4)}
        p = tmp_path / "model.pt"
        torch.save(sd, str(p))
        meta = inspect_artifact(str(p))
        assert isinstance(meta.load_format, FieldValue)
        assert meta.load_format.value == "state_dict"
        assert meta.load_format.source == "extractor"


# ===========================================================================
# Part 4: Consumer compatibility — deploy, agent, writer
# ===========================================================================

class TestDeployPrintMetadata:
    """_print_metadata works correctly with FieldValue fields."""

    def _make_meta(self, **kwargs):
        from app.cli.core.inspector import ArtifactMetadata, FieldValue

        defaults = dict(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint=FieldValue(value="raw text string", source="extractor", confidence="high"),
            output_hint=FieldValue(value="integer class label", source="extractor", confidence="high"),
            feature_count=5,
            class_labels=["pos", "neg"],
            artifact_path=str(FIXTURE),
            artifact_size_mb=0.1,
            extra={},
            raw_facts={},
            load_format=None,
            inspection_confidence="high",
            interpretation_confidence="high",
            inspection_errors=[],
        )
        defaults.update(kwargs)
        return ArtifactMetadata(**defaults)

    def test_print_metadata_does_not_crash(self, capsys):
        """_print_metadata must handle FieldValue fields without error."""
        from app.cli.commands.deploy import _print_metadata
        meta = self._make_meta()
        # Should not raise
        _print_metadata(meta)

    def test_print_metadata_shows_value_not_repr(self, capsys):
        """Output should show 'sklearn', not 'FieldValue(value=sklearn, ...)'."""
        from app.cli.commands.deploy import _print_metadata
        meta = self._make_meta()
        _print_metadata(meta)
        output = capsys.readouterr().out
        assert "sklearn" in output
        assert "FieldValue" not in output


class TestAgentWithFieldValue:
    """Agent module works with FieldValue-wrapped metadata."""

    def _make_meta(self, **kwargs):
        from app.cli.core.inspector import ArtifactMetadata, FieldValue

        defaults = dict(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint=FieldValue(value="raw text string", source="extractor", confidence="high"),
            output_hint=FieldValue(value="integer class label", source="extractor", confidence="high"),
            feature_count=5,
            class_labels=["pos", "neg"],
            artifact_path=str(FIXTURE),
            artifact_size_mb=0.1,
            extra={},
            raw_facts={},
            load_format=None,
            inspection_confidence="high",
            interpretation_confidence="high",
            inspection_errors=[],
        )
        defaults.update(kwargs)
        return ArtifactMetadata(**defaults)

    def test_build_user_prompt_with_field_value(self):
        from app.cli.core.agent import _build_user_prompt
        meta = self._make_meta()
        prompt = _build_user_prompt(meta, "/path/to/model.pkl")
        assert "sklearn" in prompt
        assert "raw text string" in prompt
        assert "integer class label" in prompt
        assert "FieldValue" not in prompt

    def test_framework_hints_with_field_value(self):
        from app.cli.core.agent import _framework_hints
        meta = self._make_meta()
        hints = _framework_hints(meta)
        # sklearn doesn't add extra hints in current implementation, but it shouldn't crash
        assert isinstance(hints, list)

    def test_framework_hints_pytorch(self):
        from app.cli.core.agent import _framework_hints
        from app.cli.core.inspector import FieldValue
        meta = self._make_meta(
            framework=FieldValue(value="pytorch", source="extractor", confidence="high"),
            extra={"layer_count": 10}
        )
        hints = _framework_hints(meta)
        assert any("PyTorch" in h for h in hints)


class TestWriterWithFieldValue:
    """write_scaffold handles FieldValue fields."""

    def _make_meta(self, **kwargs):
        from app.cli.core.inspector import ArtifactMetadata, FieldValue

        defaults = dict(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            class_name="Pipeline",
            class_hierarchy=[],
            input_hint=FieldValue(value="raw text", source="extractor", confidence="high"),
            output_hint=FieldValue(value="int label", source="extractor", confidence="high"),
            feature_count=None,
            class_labels=None,
            artifact_path=str(FIXTURE),
            artifact_size_mb=0.1,
            extra={},
            raw_facts={},
            load_format=None,
            inspection_confidence="high",
            interpretation_confidence="high",
            inspection_errors=[],
        )
        defaults.update(kwargs)
        return ArtifactMetadata(**defaults)

    def _make_answers(self):
        from app.cli.core.prompts import DeployAnswers
        return DeployAnswers(
            name="mymodel", version="v1", device="cpu",
            routing="static", sample_input="hello",
        )

    def test_write_scaffold_with_field_value(self, tmp_path):
        from app.cli.core.writer import write_scaffold

        routing = tmp_path / "routing.py"
        routing.write_text('ROUTES = {\n}\n')

        meta = self._make_meta()
        answers = self._make_answers()
        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing,
        )

        src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
        assert "Framework detected: sklearn" in src
        assert "Input hint: raw text" in src
        assert "Output hint: int label" in src
        assert "FieldValue" not in src

    def test_write_scaffold_none_field_value(self, tmp_path):
        """When framework is None (not FieldValue), scaffold still works."""
        from app.cli.core.writer import write_scaffold
        from app.cli.core.inspector import FieldValue

        routing = tmp_path / "routing.py"
        routing.write_text('ROUTES = {\n}\n')

        meta = self._make_meta(framework=None, input_hint=None, output_hint=None)
        answers = self._make_answers()
        write_scaffold(
            meta, answers, str(FIXTURE),
            models_root=str(tmp_path / "models"),
            routing_path=routing,
        )

        src = (tmp_path / "models" / "mymodel" / "v1" / "definition.py").read_text()
        assert "Framework detected: unknown" in src
        assert "None" not in [l for l in src.splitlines() if l.startswith("#")]


# ===========================================================================
# Part 5: Explain mode — FieldValue provides provenance info
# ===========================================================================

class TestFieldValueExplainMode:
    """FieldValue provides a human-readable explain string."""

    def test_explain_string(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        explanation = fv.explain()
        assert "sklearn" in explanation
        assert "extractor" in explanation
        assert "high" in explanation

    def test_explain_includes_source(self):
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="pytorch", source="llm", confidence="medium")
        explanation = fv.explain()
        assert "llm" in explanation

    def test_explain_format(self):
        """explain() returns a structured string like 'value (source: X, confidence: Y)'."""
        from app.cli.core.inspector import FieldValue

        fv = FieldValue(value="sklearn", source="extractor", confidence="high")
        explanation = fv.explain()
        assert "source:" in explanation or "extractor" in explanation
        assert "confidence:" in explanation or "high" in explanation
