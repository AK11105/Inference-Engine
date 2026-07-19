"""Issue #25 — Include sample_input in generate(), fix(), and interpretation prompts.

Tests verify that:
1. _build_user_prompt() includes sample_input when provided
2. _build_user_prompt() handles None sample_input gracefully (no crash, no section)
3. generate() passes sample_input through to the prompt
4. fix() includes sample_input AND metadata summary in the prompt
5. fix() handles None sample_input gracefully
6. Backward compatibility: callers that omit sample_input still work
7. deploy.py passes sample_input to generate() and fix()
8. fix.py passes sample_input to llm_fix()
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.cli.core.inspector import ArtifactMetadata, FieldValue

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(**kwargs) -> ArtifactMetadata:
    """Create a minimal ArtifactMetadata for testing."""
    defaults = dict(
        framework=FieldValue(value="sklearn", source="extractor", confidence="high"),
        class_name="Pipeline",
        class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
        input_hint=FieldValue(value="raw text string", source="extractor", confidence="high"),
        output_hint=FieldValue(value="integer class label", source="extractor", confidence="high"),
        feature_count=None,
        class_labels=[0, 1],
        artifact_path="models/sentiment/v1/sentiment.pkl",
        artifact_size_mb=1.5,
    )
    defaults.update(kwargs)
    return ArtifactMetadata(**defaults)


def _mock_groq_response(content: str):
    """Build a minimal mock that looks like a Groq chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


_GOOD_RESPONSE = (
    "def load(self) -> None:\n"
    "    import joblib\n"
    "    self._model = joblib.load(r'models/sentiment/v1/sentiment.pkl')\n"
    "\n"
    "def predict(self, x):\n"
    "    return int(self._model.predict([x])[0])\n"
)


# ===========================================================================
# Section 1: _build_user_prompt — sample_input inclusion
# ===========================================================================


class TestBuildUserPromptSampleInput:
    """Tests for sample_input in _build_user_prompt()."""

    def test_includes_sample_input_string(self):
        """When sample_input is a string, prompt includes it with instruction."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl", sample_input="this movie was great")

        assert "this movie was great" in prompt
        assert "sample" in prompt.lower() or "Sample" in prompt

    def test_includes_sample_input_json_list(self):
        """When sample_input is a JSON list string, prompt includes it."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/iris/v1/iris.pkl", sample_input="[1.2, 0.4, 3.1, 0.8]")

        assert "[1.2, 0.4, 3.1, 0.8]" in prompt

    def test_includes_sample_input_json_dict(self):
        """When sample_input is a JSON dict string, prompt includes it."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(
            meta, "models/test/v1/model.pkl",
            sample_input='{"text": "hello", "length": 5}',
        )

        assert '{"text": "hello", "length": 5}' in prompt

    def test_none_sample_input_excluded(self):
        """When sample_input is None, no sample input section in prompt."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl", sample_input=None)

        # Should not contain "Sample input" section
        assert "Sample input" not in prompt
        assert "sample_input" not in prompt
        # The rest of the prompt should still be valid
        assert "sklearn" in prompt
        assert "Write load() and predict()." in prompt

    def test_empty_string_sample_input_excluded(self):
        """When sample_input is empty string, no sample input section."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl", sample_input="")

        # Empty string treated as no sample input
        assert "Sample input" not in prompt

    def test_sample_input_instruction_mentions_predict(self):
        """The sample_input section must instruct the LLM about predict()."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl", sample_input="test data")

        # Must tell the LLM that predict() needs to handle this type
        assert "predict" in prompt.lower()

    def test_backward_compat_no_sample_input_arg(self):
        """Calling _build_user_prompt without sample_input kwarg still works (default None)."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        # This is the backward-compatible call — must not raise
        prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl")

        assert "sklearn" in prompt
        assert "Write load() and predict()." in prompt


# ===========================================================================
# Section 2: generate() — sample_input flows to prompt
# ===========================================================================


class TestGenerateSampleInput:
    """Tests for sample_input in generate()."""

    def test_generate_includes_sample_input_in_prompt(self, monkeypatch):
        """generate() passes sample_input to _build_user_prompt, which includes it in messages."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import generate

            generate(meta, "models/sentiment/v1/sentiment.pkl", sample_input="this movie was great")

            # Inspect the messages sent to the LLM
            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            assert "this movie was great" in user_msg

    def test_generate_without_sample_input_backward_compat(self, monkeypatch):
        """generate() without sample_input works (backward compat for existing callers)."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import generate

            # Must not raise — backward compat
            result = generate(meta, "models/sentiment/v1/sentiment.pkl")

            assert result.load_body
            assert result.predict_body

    def test_generate_with_none_sample_input(self, monkeypatch):
        """generate(sample_input=None) works — no sample section in prompt."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import generate

            generate(meta, "models/sentiment/v1/sentiment.pkl", sample_input=None)

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            assert "Sample input" not in user_msg


# ===========================================================================
# Section 3: fix() — sample_input + metadata in prompt
# ===========================================================================


class TestFixSampleInput:
    """Tests for sample_input and metadata in fix()."""

    def test_fix_includes_sample_input_in_prompt(self, monkeypatch):
        """fix() includes sample_input in the user prompt to the LLM."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            fix(
                "def load(self):\n    raise RuntimeError('broken')\ndef predict(self, x):\n    pass",
                "RuntimeError: broken",
                sample_input="this movie was great",
            )

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            assert "this movie was great" in user_msg

    def test_fix_includes_metadata_summary_in_prompt(self, monkeypatch):
        """fix() includes metadata summary (framework, class_name, etc.) in the prompt."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        meta = _make_meta()

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            fix(
                "def load(self):\n    raise RuntimeError('broken')\ndef predict(self, x):\n    pass",
                "RuntimeError: broken",
                sample_input="test input",
                meta=meta,
            )

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            # Metadata summary should include framework and class_name
            assert "sklearn" in user_msg
            assert "Pipeline" in user_msg

    def test_fix_without_sample_input_backward_compat(self, monkeypatch):
        """fix() without sample_input still works (backward compat)."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            # Must not raise — backward compat call with only required args
            result = fix(
                "def load(self):\n    self._model = None\ndef predict(self, x):\n    return x",
                "TypeError: something went wrong",
            )

            assert result.load_body
            assert result.predict_body

    def test_fix_with_none_sample_input(self, monkeypatch):
        """fix(sample_input=None) — no sample input section in prompt."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            fix(
                "def load(self):\n    pass\ndef predict(self, x):\n    pass",
                "error",
                sample_input=None,
            )

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            assert "Sample input" not in user_msg

    def test_fix_with_none_meta(self, monkeypatch):
        """fix(meta=None) — no metadata section in prompt."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            fix(
                "def load(self):\n    pass\ndef predict(self, x):\n    pass",
                "error",
                sample_input="test",
                meta=None,
            )

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            # sample_input should still be present
            assert "test" in user_msg


# ===========================================================================
# Section 4: deploy.py — passes sample_input to generate() and fix()
# ===========================================================================


class TestDeployPassesSampleInput:
    """Tests that deploy.py forwards sample_input to LLM functions."""

    def test_deploy_passes_sample_input_to_generate(self, monkeypatch, tmp_path):
        """run_deploy passes answers.sample_input to generate()."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        from app.cli.commands import deploy as deploy_mod
        from app.cli.core import writer as writer_mod
        from app.cli.core.agent import GeneratedCode

        meta = _make_meta()
        captured_kwargs = {}

        def fake_generate(m, dest, **kwargs):
            captured_kwargs.update(kwargs)
            return GeneratedCode(
                load_body="def load(self) -> None:\n    self._model = None",
                predict_body="def predict(self, x):\n    return x",
                raw="def load(self) -> None:\n    self._model = None\n\ndef predict(self, x):\n    return x",
            )

        monkeypatch.setattr(deploy_mod, "generate", fake_generate)
        monkeypatch.setattr(deploy_mod, "inspect_artifact", lambda *a, **kw: meta)
        monkeypatch.setattr(deploy_mod, "_is_interactive", lambda: False)
        monkeypatch.setattr(deploy_mod, "build_deployment_spec", lambda facts: MagicMock(deployment_readiness="ready"))

        # Mock validation loop to succeed immediately (returns the code as-is)
        monkeypatch.setattr(deploy_mod, "_run_validation_loop", lambda *a, **kw: a[3])

        # Mock writer (imported lazily inside run_deploy)
        monkeypatch.setattr(writer_mod, "write_deployment", lambda *a, **kw: None)

        # Create a dummy artifact
        artifact = tmp_path / "model.pkl"
        artifact.write_bytes(b"fake")

        from app.cli.commands.deploy import run_deploy

        run_deploy(
            str(artifact),
            name="test",
            version="v1",
            device="cpu",
            routing="static",
            sample_input="this movie was great",
            yes=True,
        )

        assert captured_kwargs.get("sample_input") == "this movie was great"

    def test_validation_loop_passes_sample_input_to_fix(self, monkeypatch, tmp_path):
        """_run_validation_loop passes sample_input to fix() on validation failure."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        from app.cli.commands import deploy as deploy_mod
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.agent import GeneratedCode
        from app.cli.core.prompts import DeployAnswers

        meta = _make_meta()
        answers = DeployAnswers(
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello world",
        )

        initial_code = GeneratedCode(
            load_body="def load(self) -> None:\n    raise RuntimeError('broken')",
            predict_body="def predict(self, x):\n    return x",
            raw="def load(self) -> None:\n    raise RuntimeError('broken')\ndef predict(self, x):\n    return x",
        )

        fix_calls = []

        def fake_fix(code, error, **kwargs):
            fix_calls.append(kwargs)
            return GeneratedCode(
                load_body="def load(self) -> None:\n    self._model = None",
                predict_body="def predict(self, x):\n    return x",
                raw="def load(self) -> None:\n    self._model = None\n\ndef predict(self, x):\n    return x",
            )

        call_count = {"n": 0}

        def fake_validate(src, inp, tmp):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return MagicMock(success=False, error="RuntimeError: broken", output=None)
            return MagicMock(success=True, error=None, output="ok")

        monkeypatch.setattr(deploy_mod, "fix", fake_fix)
        monkeypatch.setattr(deploy_mod, "validate_pipeline", fake_validate)
        monkeypatch.setattr(deploy_mod, "build_definition_source", lambda *a, **kw: "source")

        result = _run_validation_loop(meta, answers, "models/test/v1/model.pkl", initial_code)

        assert result is not None
        assert len(fix_calls) == 1
        assert fix_calls[0].get("sample_input") == "hello world"
        assert fix_calls[0].get("meta") == meta


# ===========================================================================
# Section 5: fix.py — passes sample_input to llm_fix()
# ===========================================================================


class TestFixCommandPassesSampleInput:
    """Tests that fix.py forwards sample_input to llm_fix()."""

    def test_run_fix_passes_sample_input_to_llm_fix(self, tmp_path, monkeypatch):
        """run_fix passes sample_input to the llm_fix function."""
        from app.cli.commands import fix as fix_mod
        from app.cli.commands.fix import run_fix
        from app.cli.core.agent import GeneratedCode

        # Write a definition file
        definition = tmp_path / "definition.py"
        definition.write_text(
            "class _GeneratedModel:\n"
            "    def load(self) -> None:\n"
            "        raise RuntimeError('broken')\n"
            "    def predict(self, x):\n"
            "        return x\n"
        )

        monkeypatch.setattr(fix_mod, "_is_interactive", lambda: False)

        fix_calls = []

        def fake_llm_fix(src, err, **kwargs):
            fix_calls.append(kwargs)
            return GeneratedCode(
                load_body="def load(self) -> None:\n    self._model = None",
                predict_body="def predict(self, x):\n    return x",
                raw="...",
            )

        call_count = {"n": 0}

        def fake_validate(src, inp, tmp):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return MagicMock(success=False, error="RuntimeError: broken", output=None)
            return MagicMock(success=True, error=None, output="ok")

        monkeypatch.setattr(fix_mod, "llm_fix", fake_llm_fix)
        monkeypatch.setattr(fix_mod, "validate_pipeline", fake_validate)

        # Mock _splice_methods to return something valid
        monkeypatch.setattr(fix_mod, "_splice_methods", lambda src, load, predict: src)

        # Suppress interactive confirm prompt
        monkeypatch.setattr("builtins.input", lambda _: "y")
        monkeypatch.setattr(fix_mod, "_is_interactive", lambda: True)

        run_fix(str(tmp_path), sample_input="this movie was great")

        assert len(fix_calls) >= 1
        assert fix_calls[0].get("sample_input") == "this movie was great"


# ===========================================================================
# Section 6: Interpretation prompt — already has sample_input (sanity check)
# ===========================================================================


class TestInterpretationPromptSampleInput:
    """Verify the interpretation prompt already includes sample_input correctly."""

    def test_interpretation_prompt_includes_sample_input(self):
        """_build_interpretation_prompt includes sample_input when provided."""
        from app.cli.core.interpreter import _build_interpretation_prompt
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        meta = _make_meta(raw_facts={"framework": "sklearn", "class_name": "Pipeline"})
        spec = MagicMock(spec=DeploymentSpecCandidate)
        spec.framework = "sklearn"
        spec.artifact_type = "pickle"
        spec.loader_strategy = "joblib"
        spec.required_packages = ["joblib", "scikit-learn"]
        spec.capabilities = ["classification"]
        spec.deployment_readiness = "needs_interpretation"

        prompt = _build_interpretation_prompt(meta, spec, sample_input="this movie was great")

        assert "this movie was great" in prompt
        assert "Sample Input Provided" in prompt

    def test_interpretation_prompt_excludes_when_none(self):
        """_build_interpretation_prompt excludes sample_input section when None."""
        from app.cli.core.interpreter import _build_interpretation_prompt
        from app.cli.core.spec_builder import DeploymentSpecCandidate

        meta = _make_meta(raw_facts={"framework": "sklearn", "class_name": "Pipeline"})
        spec = MagicMock(spec=DeploymentSpecCandidate)
        spec.framework = "sklearn"
        spec.artifact_type = "pickle"
        spec.loader_strategy = "joblib"
        spec.required_packages = ["joblib"]
        spec.capabilities = []
        spec.deployment_readiness = "needs_interpretation"

        prompt = _build_interpretation_prompt(meta, spec, sample_input=None)

        assert "Sample Input Provided" not in prompt


# ===========================================================================
# Section 7: Edge cases
# ===========================================================================


class TestSampleInputEdgeCases:
    """Edge cases for sample_input handling."""

    def test_sample_input_with_special_characters(self):
        """sample_input with quotes, newlines, etc. is included safely."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        special_input = 'He said "hello"\nSecond line'
        prompt = _build_user_prompt(meta, "models/test/v1/m.pkl", sample_input=special_input)

        assert 'He said "hello"' in prompt

    def test_sample_input_very_long_truncation_not_required(self):
        """Long sample_input is included as-is (no silent truncation)."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        long_input = "x" * 500
        prompt = _build_user_prompt(meta, "models/test/v1/m.pkl", sample_input=long_input)

        assert long_input in prompt

    def test_sample_input_numeric_string(self):
        """Numeric string sample_input is included correctly."""
        from app.cli.core.agent import _build_user_prompt

        meta = _make_meta()
        prompt = _build_user_prompt(meta, "models/test/v1/m.pkl", sample_input="42.5")

        assert "42.5" in prompt

    def test_fix_with_complex_sample_input(self, monkeypatch):
        """fix() with a complex JSON sample_input includes it in the prompt."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        with patch("app.cli.core.agent.Groq") as MockGroq:
            instance = MockGroq.return_value
            instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

            from app.cli.core.agent import fix

            complex_input = json.dumps({"features": [1.0, 2.0, 3.0], "category": "A"})

            fix(
                "def load(self):\n    pass\ndef predict(self, x):\n    pass",
                "error",
                sample_input=complex_input,
            )

            call_kwargs = instance.chat.completions.create.call_args
            messages = call_kwargs.kwargs["messages"]
            user_msg = messages[1]["content"]

            assert complex_input in user_msg
