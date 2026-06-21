"""Issue #18 — sample_input must be JSON-parsed before validate_pipeline."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cli.core.validator import validate_pipeline


# ---------------------------------------------------------------------------
# _parse_sample_input unit tests
# ---------------------------------------------------------------------------

class TestParseSampleInput:
    def _parse(self, raw):
        from app.cli.commands.deploy import _parse_sample_input
        return _parse_sample_input(raw)

    def test_json_array_becomes_list(self):
        assert self._parse("[1.2, 0.4, 3.1]") == [1.2, 0.4, 3.1]

    def test_json_int_becomes_int(self):
        assert self._parse("42") == 42

    def test_json_float_becomes_float(self):
        assert self._parse("3.14") == 3.14

    def test_json_object_becomes_dict(self):
        assert self._parse('{"a": 1}') == {"a": 1}

    def test_plain_string_stays_string(self):
        assert self._parse("this movie was great") == "this movie was great"

    def test_invalid_json_stays_string(self):
        assert self._parse("[not valid json") == "[not valid json"

    def test_quoted_string_becomes_python_string(self):
        # JSON "hello" → Python str
        assert self._parse('"hello"') == "hello"


# ---------------------------------------------------------------------------
# deploy._run_validation_loop passes parsed input
# ---------------------------------------------------------------------------

class TestDeployValidationLoopParsesSampleInput:
    def _make_meta(self):
        from app.cli.core.inspector import ArtifactMetadata
        return ArtifactMetadata(
            framework="sklearn", class_name="Model", class_hierarchy=[],
            input_hint="x", output_hint="y", feature_count=None,
            class_labels=None, artifact_path="/tmp/m.pkl",
            artifact_size_mb=1.0, extra={},
        )

    def _make_answers(self, sample_input):
        from app.cli.core.prompts import DeployAnswers
        return DeployAnswers(
            name="m", version="v1", device="cpu",
            routing="static", sample_input=sample_input,
        )

    def _make_code(self):
        from app.cli.core.agent import GeneratedCode
        return GeneratedCode(load_body="", predict_body="", raw="")

    def test_numeric_array_string_is_parsed_before_validate(self):
        """validate_pipeline must receive a list, not the raw string '[1.2, 0.4]'."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        received: list = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(
                self._make_meta(),
                self._make_answers("[1.2, 0.4, 3.1]"),
                "/tmp/m.pkl",
                self._make_code(),
            )

        assert received[0] == [1.2, 0.4, 3.1], (
            f"Expected list [1.2, 0.4, 3.1], got {received[0]!r}"
        )

    def test_plain_text_string_passes_through_unchanged(self):
        """A plain-text sample_input must still reach validate_pipeline as a string."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        received: list = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(
                self._make_meta(),
                self._make_answers("this movie was great"),
                "/tmp/m.pkl",
                self._make_code(),
            )

        assert received[0] == "this movie was great"

    def test_answers_raw_string_preserved_after_parse(self):
        """answers.sample_input must keep the original raw string (for curl example)."""
        from app.cli.core.prompts import DeployAnswers

        answers = DeployAnswers(
            name="m", version="v1", device="cpu",
            routing="static", sample_input="[1.2, 0.4, 3.1]",
        )
        assert answers.sample_input == "[1.2, 0.4, 3.1]"


# ---------------------------------------------------------------------------
# fix.run_fix passes parsed input
# ---------------------------------------------------------------------------

class TestFixCommandParsesSampleInput:
    def test_numeric_array_string_is_parsed_before_validate(self, tmp_path):
        """run_fix must pass a list to validate_pipeline, not the raw string."""
        from app.cli.commands.fix import run_fix
        from app.cli.core.validator import ValidationResult

        # Minimal valid definition.py with _GeneratedModel
        (tmp_path / "definition.py").write_text(
            "class _GeneratedModel:\n"
            "    def load(self): pass\n"
            "    def predict(self, x): return x\n",
            encoding="utf-8",
        )

        received: list = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.fix._is_interactive", return_value=True), \
             patch("builtins.input", return_value="[1.2, 0.4, 3.1]"), \
             patch("app.cli.commands.fix.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.fix.console"):
            run_fix(str(tmp_path))

        assert received[0] == [1.2, 0.4, 3.1], (
            f"Expected list [1.2, 0.4, 3.1], got {received[0]!r}"
        )
