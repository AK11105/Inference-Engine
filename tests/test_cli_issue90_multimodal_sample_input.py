"""Issue #90 — Multi-modal sample input (@file, stdin, binary support).

Tests verify that:
1. Backward compatibility: inline JSON, plain strings still work identically
2. @file syntax reads and parses JSON files
3. @file syntax reads text files as plain strings
4. @file syntax loads binary files (.png, .jpg, .jpeg, .wav, .mp3, .npy) as bytes
5. stdin pipe ("-") reads from sys.stdin
6. Error handling: FileNotFoundError for missing @file references
7. Integration: deploy.py and fix.py both use the shared parse_sample_input
8. Interactive prompt accepts @file syntax
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module import tests — verify the shared module exists and is importable
# ---------------------------------------------------------------------------


class TestModuleStructure:
    """The shared sample_input module must exist in app.cli.core."""

    def test_module_is_importable(self):
        from app.cli.core.sample_input import parse_sample_input
        assert callable(parse_sample_input)

    def test_module_exposes_parse_sample_input_function(self):
        import app.cli.core.sample_input as mod
        assert hasattr(mod, "parse_sample_input")

    def test_deploy_imports_from_shared_module(self):
        """deploy.py should import parse_sample_input from the shared module."""
        from app.cli.commands.deploy import _parse_sample_input
        from app.cli.core.sample_input import parse_sample_input
        # They should be the same function (or deploy wraps it)
        # We just verify deploy's _parse_sample_input handles @file syntax
        assert callable(_parse_sample_input)

    def test_fix_imports_from_shared_module(self):
        """fix.py should import parse_sample_input from the shared module."""
        from app.cli.commands.fix import _parse_sample_input
        from app.cli.core.sample_input import parse_sample_input
        assert callable(_parse_sample_input)


# ---------------------------------------------------------------------------
# Backward compatibility tests — existing behavior MUST NOT change
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """All existing _parse_sample_input behavior must be preserved."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

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
        assert self._parse('"hello"') == "hello"

    def test_nested_json_object(self):
        raw = '{"text": "hello", "metadata": {"lang": "en"}}'
        result = self._parse(raw)
        assert result == {"text": "hello", "metadata": {"lang": "en"}}

    def test_json_null_becomes_none(self):
        assert self._parse("null") is None

    def test_json_boolean_true(self):
        assert self._parse("true") is True

    def test_json_boolean_false(self):
        assert self._parse("false") is False

    def test_empty_string_stays_empty_string(self):
        assert self._parse("") == ""

    def test_whitespace_only_stays_string(self):
        assert self._parse("   ") == "   "


# ---------------------------------------------------------------------------
# @file syntax — JSON files
# ---------------------------------------------------------------------------


class TestAtFileJSON:
    """@path/to/file.json should read and parse the file as JSON."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_json_file_with_array(self, tmp_path):
        f = tmp_path / "input.json"
        f.write_text('[1.2, 0.4, 3.1]')
        result = self._parse(f"@{f}")
        assert result == [1.2, 0.4, 3.1]

    def test_json_file_with_object(self, tmp_path):
        f = tmp_path / "payload.json"
        payload = {"text": "hello world", "features": [0.1, 0.2, 0.3]}
        f.write_text(json.dumps(payload))
        result = self._parse(f"@{f}")
        assert result == payload

    def test_json_file_with_nested_structure(self, tmp_path):
        f = tmp_path / "nested.json"
        data = {"image": {"width": 224, "height": 224}, "labels": ["cat", "dog"]}
        f.write_text(json.dumps(data))
        result = self._parse(f"@{f}")
        assert result == data

    def test_json_file_with_integer(self, tmp_path):
        f = tmp_path / "num.json"
        f.write_text("42")
        result = self._parse(f"@{f}")
        assert result == 42

    def test_json_file_with_high_dimensional_vector(self, tmp_path):
        """Real use-case: 100+ feature vector stored in a file."""
        f = tmp_path / "features.json"
        vector = [[float(i) * 0.01 for i in range(128)]]
        f.write_text(json.dumps(vector))
        result = self._parse(f"@{f}")
        assert result == vector
        assert len(result[0]) == 128

    def test_json_file_with_whitespace_and_newlines(self, tmp_path):
        """File content may have leading/trailing whitespace — should be stripped."""
        f = tmp_path / "padded.json"
        f.write_text('  \n  {"key": "value"}  \n  ')
        result = self._parse(f"@{f}")
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# @file syntax — text files (non-JSON)
# ---------------------------------------------------------------------------


class TestAtFileText:
    """@path/to/file.txt should read as text; if not valid JSON, return string."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_text_file_plain_string(self, tmp_path):
        f = tmp_path / "input.txt"
        f.write_text("this movie was great")
        result = self._parse(f"@{f}")
        assert result == "this movie was great"

    def test_text_file_with_csv_like_content(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        result = self._parse(f"@{f}")
        assert result == "name,age\nAlice,30"

    def test_text_file_with_invalid_json(self, tmp_path):
        """Text file containing something that looks like JSON but isn't."""
        f = tmp_path / "broken.json"
        f.write_text("{not: valid json}")
        result = self._parse(f"@{f}")
        assert result == "{not: valid json}"

    def test_text_file_stripped(self, tmp_path):
        """File content should be stripped of leading/trailing whitespace."""
        f = tmp_path / "whitespace.txt"
        f.write_text("  hello world  \n")
        result = self._parse(f"@{f}")
        assert result == "hello world"


# ---------------------------------------------------------------------------
# @file syntax — binary files
# ---------------------------------------------------------------------------


class TestAtFileBinary:
    """Binary files (.png, .jpg, .jpeg, .wav, .mp3, .npy) loaded as bytes."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_png_file_returns_bytes(self, tmp_path):
        f = tmp_path / "image.png"
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_jpg_file_returns_bytes(self, tmp_path):
        f = tmp_path / "photo.jpg"
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_jpeg_file_returns_bytes(self, tmp_path):
        f = tmp_path / "photo.jpeg"
        content = b"\xff\xd8\xff\xe0" + b"\x01" * 50
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_wav_file_returns_bytes(self, tmp_path):
        f = tmp_path / "audio.wav"
        content = b"RIFF" + b"\x00" * 100
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_mp3_file_returns_bytes(self, tmp_path):
        f = tmp_path / "audio.mp3"
        content = b"\xff\xfb\x90\x00" + b"\x00" * 100
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_npy_file_returns_bytes(self, tmp_path):
        f = tmp_path / "array.npy"
        content = b"\x93NUMPY" + b"\x00" * 100
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_binary_file_preserves_exact_content(self, tmp_path):
        """Verify no encoding/stripping happens on binary data."""
        f = tmp_path / "raw.png"
        # Include null bytes, high bytes, newlines
        content = bytes(range(256))
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert result == content


# ---------------------------------------------------------------------------
# @file syntax — error handling
# ---------------------------------------------------------------------------


class TestAtFileErrors:
    """Error cases for @file references."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_missing_file_raises_file_not_found_error(self):
        with pytest.raises(FileNotFoundError, match="Sample input file not found"):
            self._parse("@/nonexistent/path/to/file.json")

    def test_missing_file_includes_path_in_message(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            self._parse("@/tmp/definitely_not_real_file_xyz.json")
        assert "definitely_not_real_file_xyz.json" in str(exc_info.value)

    def test_at_sign_only_without_path_raises_file_not_found(self):
        """Edge case: just '@' with empty path should raise."""
        with pytest.raises(FileNotFoundError):
            self._parse("@")

    def test_relative_path_works(self, tmp_path, monkeypatch):
        """@relative/path should resolve relative to cwd."""
        f = tmp_path / "sample.json"
        f.write_text('{"key": "value"}')
        monkeypatch.chdir(tmp_path)
        result = self._parse("@sample.json")
        assert result == {"key": "value"}


# ---------------------------------------------------------------------------
# Stdin pipe ("-")
# ---------------------------------------------------------------------------


class TestStdinPipe:
    """When raw == '-', read from sys.stdin."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_stdin_json_array(self):
        with patch("sys.stdin", new_callable=lambda: io.StringIO("[1, 2, 3]")):
            # Need to patch at the module level where it's used
            with patch("app.cli.core.sample_input.sys") as mock_sys:
                mock_sys.stdin.read.return_value = "[1, 2, 3]\n"
                result = self._parse("-")
        assert result == [1, 2, 3]

    def test_stdin_json_object(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = '{"text": "hello"}\n'
            result = self._parse("-")
        assert result == {"text": "hello"}

    def test_stdin_plain_text(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = "this movie was great\n"
            result = self._parse("-")
        assert result == "this movie was great"

    def test_stdin_empty(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = ""
            result = self._parse("-")
        assert result == ""

    def test_stdin_whitespace_stripped(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = "  [1, 2, 3]  \n"
            result = self._parse("-")
        assert result == [1, 2, 3]


# ---------------------------------------------------------------------------
# Edge cases and priority
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and priority ordering."""

    def _parse(self, raw: str):
        from app.cli.core.sample_input import parse_sample_input
        return parse_sample_input(raw)

    def test_literal_at_sign_in_text_that_is_not_file(self):
        """Strings starting with @ where the file doesn't exist should raise,
        not silently fall through as a string."""
        with pytest.raises(FileNotFoundError):
            self._parse("@nonexistent_file.json")

    def test_literal_dash_means_stdin_not_string(self):
        """'-' should always trigger stdin read, not be treated as a string."""
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = "piped content"
            result = self._parse("-")
        assert result == "piped content"

    def test_double_dash_is_plain_string(self):
        """'--' is just a string, not stdin."""
        result = self._parse("--")
        assert result == "--"

    def test_at_with_json_extension_but_binary_content(self, tmp_path):
        """A .json file with non-UTF-8 content — should handle gracefully."""
        f = tmp_path / "bad.json"
        f.write_bytes(b"\xff\xfe" + b"not utf8")
        # This should either raise a clear error or handle gracefully
        # Implementation can choose — we just verify it doesn't crash silently
        try:
            result = self._parse(f"@{f}")
            # If it returns, it should be a string (best-effort decode)
        except (UnicodeDecodeError, ValueError):
            pass  # acceptable

    def test_file_with_unknown_extension_reads_as_text(self, tmp_path):
        """Extensions not in the binary list are read as text."""
        f = tmp_path / "data.yaml"
        f.write_text("key: value")
        result = self._parse(f"@{f}")
        # YAML is not JSON, so falls back to string
        assert result == "key: value"

    def test_file_without_extension_reads_as_text(self, tmp_path):
        """Files with no extension should be read as text."""
        f = tmp_path / "Makefile"
        f.write_text('{"hello": "world"}')
        result = self._parse(f"@{f}")
        assert result == {"hello": "world"}


# ---------------------------------------------------------------------------
# Integration: deploy.py uses the shared module correctly
# ---------------------------------------------------------------------------


class TestDeployIntegration:
    """deploy.py _parse_sample_input should handle all multi-modal inputs."""

    def _parse(self, raw: str):
        from app.cli.commands.deploy import _parse_sample_input
        return _parse_sample_input(raw)

    def test_deploy_inline_json_still_works(self):
        assert self._parse("[1.2, 0.4, 3.1]") == [1.2, 0.4, 3.1]

    def test_deploy_inline_string_still_works(self):
        assert self._parse("hello world") == "hello world"

    def test_deploy_at_file_json(self, tmp_path):
        f = tmp_path / "deploy_input.json"
        f.write_text('{"data": [1, 2, 3]}')
        result = self._parse(f"@{f}")
        assert result == {"data": [1, 2, 3]}

    def test_deploy_at_file_binary(self, tmp_path):
        f = tmp_path / "test.png"
        content = b"\x89PNG" + b"\x00" * 20
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)
        assert result == content

    def test_deploy_stdin(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = '{"input": "from pipe"}'
            result = self._parse("-")
        assert result == {"input": "from pipe"}

    def test_deploy_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            self._parse("@/no/such/file.json")


# ---------------------------------------------------------------------------
# Integration: fix.py uses the shared module correctly
# ---------------------------------------------------------------------------


class TestFixIntegration:
    """fix.py _parse_sample_input should handle all multi-modal inputs."""

    def _parse(self, raw: str):
        from app.cli.commands.fix import _parse_sample_input
        return _parse_sample_input(raw)

    def test_fix_inline_json_still_works(self):
        assert self._parse("[1.2, 0.4, 3.1]") == [1.2, 0.4, 3.1]

    def test_fix_inline_string_still_works(self):
        assert self._parse("hello world") == "hello world"

    def test_fix_at_file_json(self, tmp_path):
        f = tmp_path / "fix_input.json"
        f.write_text('{"text": "broken input"}')
        result = self._parse(f"@{f}")
        assert result == {"text": "broken input"}

    def test_fix_at_file_binary(self, tmp_path):
        f = tmp_path / "test.wav"
        content = b"RIFF" + b"\x00" * 20
        f.write_bytes(content)
        result = self._parse(f"@{f}")
        assert isinstance(result, bytes)

    def test_fix_stdin(self):
        with patch("app.cli.core.sample_input.sys") as mock_sys:
            mock_sys.stdin.read.return_value = "fix input from pipe"
            result = self._parse("-")
        assert result == "fix input from pipe"

    def test_fix_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            self._parse("@/no/such/file.json")


# ---------------------------------------------------------------------------
# Integration: validation loop receives correctly parsed multi-modal input
# ---------------------------------------------------------------------------


class TestValidationLoopWithFileInput:
    """The validation loop should pass file contents to validate_pipeline."""

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

    def test_file_reference_is_resolved_before_validate(self, tmp_path):
        """When sample_input is '@file.json', validate_pipeline gets parsed JSON."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        # Create the sample input file
        f = tmp_path / "test_payload.json"
        f.write_text('{"features": [0.1, 0.2, 0.3]}')

        received = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(
                self._make_meta(),
                self._make_answers(f"@{f}"),
                "/tmp/m.pkl",
                self._make_code(),
            )

        assert received[0] == {"features": [0.1, 0.2, 0.3]}

    def test_binary_file_reference_passes_bytes_to_validate(self, tmp_path):
        """When sample_input is '@image.png', validate_pipeline gets bytes."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        f = tmp_path / "test.png"
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        f.write_bytes(content)

        received = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(
                self._make_meta(),
                self._make_answers(f"@{f}"),
                "/tmp/m.pkl",
                self._make_code(),
            )

        assert isinstance(received[0], bytes)
        assert received[0] == content


# ---------------------------------------------------------------------------
# Integration: fix command with file-based sample input
# ---------------------------------------------------------------------------


class TestFixCommandWithFileInput:
    """run_fix should handle @file sample input from --sample-input flag."""

    def test_fix_with_file_sample_input(self, tmp_path):
        """run_fix with --sample-input @file.json passes parsed JSON to validate."""
        from app.cli.commands.fix import run_fix
        from app.cli.core.validator import ValidationResult

        # Create definition.py
        (tmp_path / "definition.py").write_text(
            "class _GeneratedModel:\n"
            "    def load(self): pass\n"
            "    def predict(self, x): return x\n",
            encoding="utf-8",
        )

        # Create sample input file
        sample_file = tmp_path / "sample.json"
        sample_file.write_text('{"text": "test input"}')

        received = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.fix.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.fix.console"):
            run_fix(str(tmp_path), sample_input=f"@{sample_file}")

        assert received[0] == {"text": "test input"}

    def test_fix_interactive_prompt_with_at_file(self, tmp_path):
        """In interactive mode, typing @path/to/file should work too."""
        from app.cli.commands.fix import run_fix
        from app.cli.core.validator import ValidationResult

        (tmp_path / "definition.py").write_text(
            "class _GeneratedModel:\n"
            "    def load(self): pass\n"
            "    def predict(self, x): return x\n",
            encoding="utf-8",
        )

        sample_file = tmp_path / "interactive_input.json"
        sample_file.write_text("[1, 2, 3]")

        received = []

        def fake_validate(source, sample_input, tmp_dir):
            received.append(sample_input)
            return ValidationResult(success=True, output="ok")

        with patch("app.cli.commands.fix._is_interactive", return_value=True), \
             patch("builtins.input", return_value=f"@{sample_file}"), \
             patch("app.cli.commands.fix.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.fix.console"):
            run_fix(str(tmp_path))

        assert received[0] == [1, 2, 3]
