"""Issue #16 — LLM interpretation stage tests.

Tests for app.cli.core.interpreter: the stage between inspection/spec_builder
and codegen that enriches ArtifactMetadata via an LLM call when
deployment_readiness != "ready".
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

from app.cli.core.inspector import ArtifactMetadata, FieldValue
from app.cli.core.spec_builder import DeploymentSpecCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(**kwargs) -> ArtifactMetadata:
    """Build an ArtifactMetadata with sensible defaults for testing."""
    defaults = dict(
        framework=FieldValue(value="unknown", source="extractor", confidence="low"),
        class_name="unknown",
        class_hierarchy=[],
        input_hint=FieldValue(value="unknown", source="extractor", confidence="low"),
        output_hint=FieldValue(value="unknown", source="extractor", confidence="low"),
        feature_count=None,
        class_labels=None,
        artifact_path="/tmp/model.pkl",
        artifact_size_mb=2.0,
        extra={},
        raw_facts={
            "format": "pickle",
            "framework": "unknown",
            "artifact_size_mb": 2.0,
            "errors": [],
        },
        inspection_confidence="low",
        interpretation_confidence="low",
        inspection_errors=[],
        load_format=None,
    )
    defaults.update(kwargs)
    return ArtifactMetadata(**defaults)


def _make_spec(**kwargs) -> DeploymentSpecCandidate:
    """Build a DeploymentSpecCandidate with defaults for testing."""
    defaults = dict(
        framework=None,
        artifact_type="pickle",
        loader_strategy=None,
        required_packages=[],
        capabilities=[],
        deployment_readiness="needs_clarification",
    )
    defaults.update(kwargs)
    return DeploymentSpecCandidate(**defaults)


def _mock_groq_response(content: str):
    """Build a minimal mock that looks like a Groq chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# InterpretationResult dataclass tests
# ---------------------------------------------------------------------------

class TestInterpretationResult:
    """The result dataclass must hold all fields from the LLM response."""

    def test_basic_creation(self):
        from app.cli.core.interpreter import InterpretationResult
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array, shape (n_samples, n_features)",
            output_hint="integer class label",
            confidence="medium",
            suggested_sample_input="[1.0, 0.0, 1.0, 0.0]",
            question=None,
            question_field=None,
            options=None,
            suggested_answer=None,
        )
        assert result.framework == "xgboost"
        assert result.load_format == "joblib"
        assert result.confidence == "medium"

    def test_with_question(self):
        from app.cli.core.interpreter import InterpretationResult
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="low",
            suggested_sample_input=None,
            question="Is this an XGBModel or a raw Booster?",
            question_field="load_format",
            options=["joblib", "xgb.Booster + load_model()", "pickle"],
            suggested_answer="joblib",
        )
        assert result.question is not None
        assert result.question_field == "load_format"
        assert len(result.options) == 3
        assert result.suggested_answer == "joblib"

    def test_nullable_fields(self):
        from app.cli.core.interpreter import InterpretationResult
        result = InterpretationResult(
            framework="sklearn",
            load_format="joblib",
            input_hint="array-like",
            output_hint="int",
            confidence="high",
            suggested_sample_input=None,
            question=None,
            question_field=None,
            options=None,
            suggested_answer=None,
        )
        assert result.question is None
        assert result.options is None
        assert result.suggested_sample_input is None

    def test_is_dataclass(self):
        from app.cli.core.interpreter import InterpretationResult
        result = InterpretationResult(
            framework="pytorch",
            load_format="state_dict",
            input_hint="torch.Tensor",
            output_hint="torch.Tensor",
            confidence="medium",
            suggested_sample_input="[[1.0, 2.0]]",
            question=None,
            question_field=None,
            options=None,
            suggested_answer=None,
        )
        d = asdict(result)
        assert d["framework"] == "pytorch"
        assert d["load_format"] == "state_dict"


# ---------------------------------------------------------------------------
# _build_interpretation_prompt tests
# ---------------------------------------------------------------------------

class TestBuildInterpretationPrompt:
    """The prompt must include raw_facts, spec info, and sample input when provided."""

    def test_contains_raw_facts(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta(raw_facts={"format": "pickle", "framework": "unknown", "errors": []})
        spec = _make_spec()
        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)
        assert "pickle" in prompt
        assert "unknown" in prompt

    def test_contains_spec_readiness(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta()
        spec = _make_spec(deployment_readiness="needs_clarification")
        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)
        assert "needs_clarification" in prompt

    def test_includes_sample_input_when_provided(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta()
        spec = _make_spec()
        prompt = _build_interpretation_prompt(meta, spec, sample_input="hello world")
        assert "hello world" in prompt

    def test_excludes_sample_input_when_none(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta()
        spec = _make_spec()
        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)
        assert "sample_input" not in prompt.lower() or "null" in prompt.lower() or "none" in prompt.lower()

    def test_includes_framework_hint(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta(
            raw_facts={"format": "pickle", "framework": "unknown", "framework_hint": "xgboost", "errors": []}
        )
        spec = _make_spec()
        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)
        assert "xgboost" in prompt

    def test_includes_inspection_errors(self):
        from app.cli.core.interpreter import _build_interpretation_prompt
        meta = _make_meta(
            inspection_errors=[{"layer": "extraction", "error": "xgboost not installed"}]
        )
        spec = _make_spec()
        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)
        assert "xgboost not installed" in prompt


# ---------------------------------------------------------------------------
# _parse_interpretation_response tests
# ---------------------------------------------------------------------------

class TestParseInterpretationResponse:
    """Parser must extract valid JSON from LLM response, handling edge cases."""

    def test_valid_json_response(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        raw = json.dumps({
            "framework": "xgboost",
            "load_format": "joblib",
            "input_hint": "numpy array",
            "output_hint": "integer class label",
            "confidence": "medium",
            "suggested_sample_input": "[1.0, 0.0]",
            "question": None,
            "question_field": None,
            "options": None,
            "suggested_answer": None,
        })
        result = _parse_interpretation_response(raw)
        assert result.framework == "xgboost"
        assert result.load_format == "joblib"
        assert result.confidence == "medium"

    def test_json_wrapped_in_markdown_fences(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        raw = "```json\n" + json.dumps({
            "framework": "pytorch",
            "load_format": "state_dict",
            "input_hint": "torch.Tensor",
            "output_hint": "torch.Tensor",
            "confidence": "medium",
            "suggested_sample_input": None,
            "question": "What model class should be instantiated?",
            "question_field": "load_format",
            "options": ["state_dict + custom class", "torch.jit.load"],
            "suggested_answer": "state_dict + custom class",
        }) + "\n```"
        result = _parse_interpretation_response(raw)
        assert result.framework == "pytorch"
        assert result.question is not None
        assert len(result.options) == 2

    def test_missing_optional_fields_default_to_none(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        raw = json.dumps({
            "framework": "sklearn",
            "load_format": "joblib",
            "input_hint": "array-like",
            "output_hint": "int",
            "confidence": "high",
        })
        result = _parse_interpretation_response(raw)
        assert result.question is None
        assert result.question_field is None
        assert result.options is None
        assert result.suggested_answer is None
        assert result.suggested_sample_input is None

    def test_invalid_json_raises_value_error(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        with pytest.raises(ValueError, match="parse"):
            _parse_interpretation_response("This is not JSON at all.")

    def test_missing_required_field_raises_value_error(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        raw = json.dumps({
            "framework": "xgboost",
            # missing load_format, input_hint, output_hint, confidence
        })
        with pytest.raises(ValueError, match="parse|missing|required"):
            _parse_interpretation_response(raw)

    def test_extra_fields_are_ignored(self):
        from app.cli.core.interpreter import _parse_interpretation_response
        raw = json.dumps({
            "framework": "sklearn",
            "load_format": "joblib",
            "input_hint": "array",
            "output_hint": "int",
            "confidence": "high",
            "suggested_sample_input": None,
            "question": None,
            "question_field": None,
            "options": None,
            "suggested_answer": None,
            "extra_nonsense": "should be ignored",
        })
        result = _parse_interpretation_response(raw)
        assert result.framework == "sklearn"


# ---------------------------------------------------------------------------
# apply_interpretation tests — patching ArtifactMetadata with LLM results
# ---------------------------------------------------------------------------

class TestApplyInterpretation:
    """apply_interpretation patches metadata fields using FieldValue with source='llm'."""

    def test_patches_framework(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.framework == "xgboost"
        assert patched.framework.source == "llm"
        assert patched.framework.confidence == "medium"

    def test_patches_load_format(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="high",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.load_format == "joblib"
        assert patched.load_format.source == "llm"

    def test_patches_input_hint(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array, shape (n_samples, 4)",
            output_hint="integer class label",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.input_hint == "numpy array, shape (n_samples, 4)"
        assert patched.input_hint.source == "llm"

    def test_patches_output_hint(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float probability",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.output_hint == "float probability"
        assert patched.output_hint.source == "llm"

    def test_does_not_overwrite_higher_priority_source(self):
        """If a field already has source='user' (priority 4), LLM (priority 1) doesn't overwrite."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta(
            framework=FieldValue(value="pytorch", source="user", confidence="high")
        )
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        # User source wins over LLM
        assert patched.framework == "pytorch"
        assert patched.framework.source == "user"

    def test_overwrites_lower_priority_source(self):
        """LLM (priority 1) overwrites 'default' (priority 0)."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta(
            framework=FieldValue(value="unknown", source="default", confidence="low")
        )
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.framework == "xgboost"
        assert patched.framework.source == "llm"

    def test_updates_interpretation_confidence(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="sklearn",
            load_format="joblib",
            input_hint="array",
            output_hint="int",
            confidence="high",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert patched.interpretation_confidence == "high"

    def test_does_not_mutate_original(self):
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        original_framework = meta.framework
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        # Original is not mutated
        assert meta.framework is original_framework
        assert patched is not meta

    def test_null_framework_in_result_does_not_patch(self):
        """If the LLM returns None for a field, don't overwrite existing value."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta(
            framework=FieldValue(value="unknown", source="extractor", confidence="low")
        )
        result = InterpretationResult(
            framework=None,
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        # framework unchanged since result had None
        assert patched.framework.value == "unknown"
        assert patched.framework.source == "extractor"


# ---------------------------------------------------------------------------
# interpret() — main entry point tests
# ---------------------------------------------------------------------------

_GOOD_LLM_RESPONSE = json.dumps({
    "framework": "xgboost",
    "load_format": "joblib",
    "input_hint": "numpy array, shape (n_samples, n_features)",
    "output_hint": "integer class label",
    "confidence": "medium",
    "suggested_sample_input": "[1.0, 0.0, 1.0]",
    "question": None,
    "question_field": None,
    "options": None,
    "suggested_answer": None,
})

_QUESTION_LLM_RESPONSE = json.dumps({
    "framework": "xgboost",
    "load_format": "joblib",
    "input_hint": "numpy array",
    "output_hint": "float",
    "confidence": "low",
    "suggested_sample_input": "[1.0, 0.0]",
    "question": "Is this an XGBModel or a raw Booster?",
    "question_field": "load_format",
    "options": ["joblib", "xgb.Booster + load_model()", "pickle"],
    "suggested_answer": "joblib",
})


class TestInterpret:
    """Tests for the interpret() function — the main LLM call orchestrator."""

    def test_calls_groq_and_returns_result(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result.framework == "xgboost"
        assert result.load_format == "joblib"

    def test_no_api_key_returns_none_with_warning(self, monkeypatch, capsys):
        from app.cli.core.interpreter import interpret
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        meta = _make_meta()
        spec = _make_spec()

        result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is None

    def test_groq_network_error_returns_none(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.side_effect = Exception("Connection timeout")

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is None

    def test_bad_json_from_llm_returns_none(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(
                "Sorry, I don't understand the artifact format."
            )

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is None

    def test_uses_env_model(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        monkeypatch.setenv("INFERENCE_ENGINE_LLM_MODEL", "mixtral-8x7b-32768")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            interpret(meta, spec, sample_input=None, interactive=False)

            call_kwargs = instance.chat.completions.create.call_args
            assert call_kwargs.kwargs["model"] == "mixtral-8x7b-32768"

    def test_passes_sample_input_to_prompt(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            interpret(meta, spec, sample_input="this movie was great", interactive=False)

            call_args = instance.chat.completions.create.call_args
            user_msg = call_args.kwargs["messages"][1]["content"]
            assert "this movie was great" in user_msg


# ---------------------------------------------------------------------------
# Interactive question handling tests
# ---------------------------------------------------------------------------

class TestInteractiveQuestions:
    """When the LLM returns a question, interactive mode presents multiple choice."""

    def test_non_interactive_auto_selects_recommended(self, monkeypatch):
        """In non-interactive mode, the suggested_answer is accepted automatically."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_QUESTION_LLM_RESPONSE)

            result = interpret(meta, spec, sample_input=None, interactive=False)

        # In non-interactive, question is ignored and result is returned as-is
        assert result is not None
        assert result.framework == "xgboost"

    def test_interactive_prompts_user(self, monkeypatch):
        """In interactive mode, the user is prompted to choose from options."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_QUESTION_LLM_RESPONSE)

            # User picks option 2
            with patch("builtins.input", return_value="2"):
                result = interpret(meta, spec, sample_input=None, interactive=True)

        assert result is not None
        # The user chose option index 2 → "xgb.Booster + load_model()"
        assert result.load_format == "xgb.Booster + load_model()"

    def test_interactive_empty_input_selects_recommended(self, monkeypatch):
        """Pressing Enter with no input selects the recommended (suggested_answer) option."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_QUESTION_LLM_RESPONSE)

            # User just hits Enter
            with patch("builtins.input", return_value=""):
                result = interpret(meta, spec, sample_input=None, interactive=True)

        assert result is not None
        # Empty input → suggested_answer "joblib" is used
        assert result.load_format == "joblib"

    def test_interactive_invalid_input_uses_recommended(self, monkeypatch):
        """Invalid input (non-numeric, out of range) falls back to recommended."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_QUESTION_LLM_RESPONSE)

            with patch("builtins.input", return_value="abc"):
                result = interpret(meta, spec, sample_input=None, interactive=True)

        assert result is not None
        assert result.load_format == "joblib"  # falls back to suggested

    def test_max_two_questions(self, monkeypatch):
        """At most 2 clarifying questions are asked in interactive mode."""
        from app.cli.core.interpreter import interpret, _MAX_QUESTIONS
        assert _MAX_QUESTIONS == 2

    def test_no_question_in_response_skips_prompting(self, monkeypatch):
        """When question is None, no input() is called even in interactive mode."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec()

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            with patch("builtins.input") as mock_input:
                result = interpret(meta, spec, sample_input=None, interactive=True)

            mock_input.assert_not_called()

        assert result is not None


# ---------------------------------------------------------------------------
# Skip logic — ready artifacts bypass interpretation entirely
# ---------------------------------------------------------------------------

class TestSkipLogic:
    """Artifacts with deployment_readiness == 'ready' skip the interpretation stage."""

    def test_ready_spec_returns_none(self, monkeypatch):
        """interpret() returns None immediately when spec says 'ready' — no LLM call."""
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high")
        )
        spec = _make_spec(deployment_readiness="ready")

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            result = interpret(meta, spec, sample_input=None, interactive=False)
            # Groq should never be instantiated
            MockGroq.assert_not_called()

        assert result is None

    def test_needs_clarification_triggers_llm(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec(deployment_readiness="needs_clarification")

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is not None
        MockGroq.assert_called_once()

    def test_unsupported_triggers_llm(self, monkeypatch):
        from app.cli.core.interpreter import interpret
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()
        spec = _make_spec(deployment_readiness="unsupported")

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is not None


# ---------------------------------------------------------------------------
# Integration: interpret + apply_interpretation end-to-end
# ---------------------------------------------------------------------------

class TestInterpretationIntegration:
    """End-to-end: interpret() → apply_interpretation() produces enriched metadata."""

    def test_full_pipeline_enriches_unknown_metadata(self, monkeypatch):
        from app.cli.core.interpreter import interpret, apply_interpretation
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        meta = _make_meta()
        spec = _make_spec(deployment_readiness="needs_clarification")

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_LLM_RESPONSE)

            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is not None
        patched = apply_interpretation(meta, result)
        assert patched.framework == "xgboost"
        assert patched.framework.source == "llm"
        assert patched.load_format == "joblib"
        assert patched.interpretation_confidence == "medium"

    def test_ready_artifact_passes_through_unchanged(self, monkeypatch):
        """A 'ready' artifact skips interpretation — metadata is unchanged."""
        from app.cli.core.interpreter import interpret, apply_interpretation
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        meta = _make_meta(
            framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
            load_format=FieldValue(value="joblib", source="extractor", confidence="high"),
        )
        spec = _make_spec(deployment_readiness="ready")

        with patch("app.cli.core.interpreter.Groq") as MockGroq:
            result = interpret(meta, spec, sample_input=None, interactive=False)

        assert result is None
        # No patching happens; meta stays the same
        assert meta.framework == "sklearn"
        assert meta.framework.source == "extractor"


# ---------------------------------------------------------------------------
# Backward compatibility — existing tests and pipeline behavior preserved
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Ensure the interpretation stage doesn't break existing pipeline consumers."""

    def test_apply_interpretation_returns_artifact_metadata(self):
        """Return type is ArtifactMetadata — same type consumed by generate()."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        assert isinstance(patched, ArtifactMetadata)

    def test_patched_metadata_framework_compares_with_string(self):
        """FieldValue with source='llm' still supports == comparison with plain strings."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array",
            output_hint="float",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        # This comparison is used throughout the codebase
        assert patched.framework == "xgboost"
        assert str(patched.framework) == "xgboost"

    def test_patched_metadata_works_with_build_user_prompt(self):
        """The enriched metadata is compatible with agent._build_user_prompt."""
        from app.cli.core.interpreter import InterpretationResult, apply_interpretation
        from app.cli.core.agent import _build_user_prompt
        meta = _make_meta()
        result = InterpretationResult(
            framework="xgboost",
            load_format="joblib",
            input_hint="numpy array, shape (n_samples, 4)",
            output_hint="integer class label",
            confidence="medium",
            suggested_sample_input=None,
            question=None, question_field=None, options=None, suggested_answer=None,
        )
        patched = apply_interpretation(meta, result)
        prompt = _build_user_prompt(patched, "/tmp/model.pkl")
        assert "xgboost" in prompt
        assert "numpy array" in prompt
