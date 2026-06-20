"""CLI Phase 8b — validation retry uses a fresh tmp dir per attempt (#23)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(framework="generic"):
    from app.cli.core.inspector import ArtifactMetadata
    return ArtifactMetadata(
        framework=framework,
        class_name="Model",
        class_hierarchy=[],
        input_hint="x",
        output_hint="y",
        feature_count=None,
        class_labels=None,
        artifact_path=str(FIXTURE),
        artifact_size_mb=1.0,
        extra={},
    )


def _make_answers(sample_input="test"):
    from app.cli.core.prompts import DeployAnswers
    return DeployAnswers(
        name="retry_test",
        version="v1",
        device="cpu",
        routing="static",
        sample_input=sample_input,
    )


def _make_code(load_body="", predict_body="", raw=""):
    from app.cli.core.agent import GeneratedCode
    return GeneratedCode(load_body=load_body, predict_body=predict_body, raw=raw)


# ---------------------------------------------------------------------------
# #23 — each retry must receive a distinct tmp_dir
# ---------------------------------------------------------------------------

class TestValidationRetryTmpDir:
    """_run_validation_loop must pass a distinct tmp_dir for every attempt."""

    def test_each_attempt_gets_distinct_tmp_dir(self):
        """validate_pipeline is called with a different path on every attempt."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        seen_dirs: list[Path] = []

        def fake_validate(source, sample_input, tmp_dir):
            seen_dirs.append(tmp_dir)
            return ValidationResult(success=False, error="boom")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.fix", return_value=_make_code()), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(_make_meta(), _make_answers(), "/tmp/m.pkl", _make_code())

        # All three attempts must have been called
        assert len(seen_dirs) == 3
        # Every path must be unique
        assert len(set(seen_dirs)) == 3, (
            "Same tmp_dir reused across attempts — stale module state possible"
        )

    def test_each_attempt_tmp_dir_exists_when_called(self):
        """The tmp_dir passed to validate_pipeline must actually exist at call time."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        dirs_existed: list[bool] = []

        def fake_validate(source, sample_input, tmp_dir):
            dirs_existed.append(tmp_dir.exists())
            return ValidationResult(success=False, error="boom")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.fix", return_value=_make_code()), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(_make_meta(), _make_answers(), "/tmp/m.pkl", _make_code())

        assert all(dirs_existed), "tmp_dir did not exist when validate_pipeline was called"

    def test_each_attempt_tmp_dir_is_under_common_root(self):
        """All per-attempt dirs should share a single parent (one TemporaryDirectory)."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        seen_dirs: list[Path] = []

        def fake_validate(source, sample_input, tmp_dir):
            seen_dirs.append(tmp_dir)
            return ValidationResult(success=False, error="boom")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.fix", return_value=_make_code()), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(_make_meta(), _make_answers(), "/tmp/m.pkl", _make_code())

        parents = {d.parent for d in seen_dirs}
        assert len(parents) == 1, (
            "Expected all attempt dirs under a single root tmp dir"
        )

    def test_stale_file_from_previous_attempt_not_visible(self):
        """
        A .py written during attempt N must not appear in attempt N+1's directory.
        Without the fix (shared dir), definition.py written in attempt 1 would still
        be present for attempt 2 before validate_pipeline overwrites it, risking a
        stale-module read window.
        With the fix, the new dir is empty when the call begins.
        """
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        stale_seen: list[bool] = []
        call_count = 0

        def fake_validate(source, sample_input, tmp_dir):
            nonlocal call_count
            # On attempt 2+ check whether a definition.py was left over from a prior attempt
            stale_seen.append((tmp_dir / "definition.py").exists())
            # Write one as validate_pipeline would
            (tmp_dir / "definition.py").write_text(source or "# placeholder", encoding="utf-8")
            call_count += 1
            return ValidationResult(success=False, error="boom")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.fix", return_value=_make_code()), \
             patch("app.cli.commands.deploy.console"):
            _run_validation_loop(_make_meta(), _make_answers(), "/tmp/m.pkl", _make_code())

        # None of the dirs should already contain definition.py when the call starts
        assert not any(stale_seen), (
            "definition.py from a previous attempt was visible in the next attempt's dir"
        )

    def test_success_on_second_attempt_returns_code(self):
        """A pass on attempt 2 should return the code; the stale-dir bug would cause attempt 3
        to re-fail, but here we only need to verify the happy path still works."""
        from app.cli.commands.deploy import _run_validation_loop
        from app.cli.core.validator import ValidationResult

        attempt = 0

        def fake_validate(source, sample_input, tmp_dir):
            nonlocal attempt
            attempt += 1
            if attempt == 2:
                return ValidationResult(success=True, output="ok")
            return ValidationResult(success=False, error="boom")

        good_code = _make_code(raw="good")

        with patch("app.cli.commands.deploy.validate_pipeline", side_effect=fake_validate), \
             patch("app.cli.commands.deploy.build_definition_source", return_value=""), \
             patch("app.cli.commands.deploy.fix", return_value=good_code), \
             patch("app.cli.commands.deploy.console"):
            result = _run_validation_loop(_make_meta(), _make_answers(), "/tmp/m.pkl", _make_code())

        assert result is not None
        assert attempt == 2  # stopped as soon as it passed
