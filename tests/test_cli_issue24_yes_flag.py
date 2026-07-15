"""Issue #24 — --yes flag for CI mode.

Tests that --yes on deploy and fix:
  1. Skips all confirmation prompts (deserialization gate, write confirmation)
  2. Skips clarifying questions from the LLM interpretation stage
  3. Uses suggested_sample_input from interpretation when no --sample-input provided
  4. Replaces all implicit _is_interactive() checks for prompt-skipping logic
  5. Works via argparse (the flag is registered on both subcommands)
  6. Backward-compatible: without --yes, existing behavior is preserved
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"


def _venv_python() -> str:
    for candidate in (
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


# ===========================================================================
# Section 1: --yes flag is registered on both subcommands (argparse level)
# ===========================================================================


class TestYesFlagRegistered:
    """The --yes flag must be accepted by argparse without error."""

    def test_deploy_accepts_yes_flag(self):
        """--yes is recognized by the deploy subcommand."""
        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "deploy", str(FIXTURE),
                "--name", "test", "--version", "v1",
                "--device", "cpu", "--routing", "static",
                "--sample-input", "hello", "--yes",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
            env={**__import__("os").environ, "GROQ_API_KEY": ""},
        )
        # May fail later (no API key), but must NOT fail at argparse level
        assert "unrecognized arguments: --yes" not in result.stderr
        assert "unrecognized arguments: --yes" not in result.stdout

    def test_fix_accepts_yes_flag(self, tmp_path):
        """--yes is recognized by the fix subcommand."""
        # Create a dummy definition.py so fix doesn't exit immediately
        defn = tmp_path / "definition.py"
        defn.write_text("class _GeneratedModel:\n    pass\n")

        result = subprocess.run(
            [
                _venv_python(), "-m", "app.cli", "fix", str(tmp_path),
                "--sample-input", "hello", "--yes",
            ],
            capture_output=True, text=True, cwd=str(ROOT),
            env={**__import__("os").environ, "GROQ_API_KEY": ""},
        )
        assert "unrecognized arguments: --yes" not in result.stderr
        assert "unrecognized arguments: --yes" not in result.stdout

    def test_deploy_help_mentions_yes(self):
        """--yes appears in deploy --help output."""
        result = subprocess.run(
            [_venv_python(), "-m", "app.cli", "deploy", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert "--yes" in result.stdout

    def test_fix_help_mentions_yes(self):
        """--yes appears in fix --help output."""
        result = subprocess.run(
            [_venv_python(), "-m", "app.cli", "fix", "--help"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert "--yes" in result.stdout


# ===========================================================================
# Section 2: deploy --yes skips deserialization confirmation prompt
# ===========================================================================


class TestDeployYesSkipsDeserializationPrompt:
    """With --yes, deploy skips the 'Continue with deserialization?' prompt."""

    def test_yes_auto_approves_allow_load(self, monkeypatch):
        """--yes implies allow_load=True without prompting."""
        from app.cli.commands.deploy import run_deploy
        from app.cli.core.agent import GeneratedCode

        # Track whether input() was ever called
        input_called = {"called": False}

        def spy_input(prompt=""):
            input_called["called"] = True
            return "y"

        monkeypatch.setattr("builtins.input", spy_input)

        # Mock the pipeline to short-circuit after inspection
        monkeypatch.setattr(
            "app.cli.commands.deploy.inspect_artifact",
            lambda path, **kw: MagicMock(
                framework="sklearn", class_name="Pipeline",
                class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
                input_hint="text", output_hint="int",
                feature_count=None, class_labels=[0, 1],
                artifact_path=str(FIXTURE), artifact_size_mb=1.0,
                raw_facts={}, extra={},
            ),
        )

        # Use dry_run to skip the rest of the pipeline
        run_deploy(
            str(FIXTURE),
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            dry_run=True, yes=True,
        )

        # input() must NOT have been called — --yes skips the prompt
        assert not input_called["called"]

    def test_yes_sets_allow_load_true(self, monkeypatch):
        """--yes + no explicit --allow-load still enables deserialization."""
        from app.cli.commands.deploy import run_deploy

        captured_kwargs = {}

        def capture_inspect(path, **kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock(
                framework="sklearn", class_name="Pipeline",
                class_hierarchy=[], input_hint="text", output_hint="int",
                feature_count=None, class_labels=None,
                artifact_path=str(FIXTURE), artifact_size_mb=1.0,
                raw_facts={}, extra={},
            )

        monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", capture_inspect)

        run_deploy(
            str(FIXTURE),
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            dry_run=True, yes=True,
        )

        assert captured_kwargs.get("allow_load") is True


# ===========================================================================
# Section 3: deploy --yes skips write confirmation prompt
# ===========================================================================


class TestDeployYesSkipsWriteConfirmation:
    """With --yes, deploy writes files without asking 'Write these files?'."""

    def test_yes_writes_without_prompting(self, monkeypatch):
        """--yes auto-approves the write step — no input() call at the end."""
        from app.cli.commands.deploy import run_deploy
        from app.cli.core.agent import GeneratedCode
        from app.cli.core.inspector import ArtifactMetadata

        meta = ArtifactMetadata(
            framework="sklearn", class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint="raw text string", output_hint="integer class label",
            feature_count=None, class_labels=[0, 1],
            artifact_path=str(FIXTURE), artifact_size_mb=1.5,
        )

        good_load = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
        good_predict = "def predict(self, x):\n    return int(self._model.predict([x])[0])"
        good_code = GeneratedCode(load_body=good_load, predict_body=good_predict, raw="")

        monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p, **kw: meta)
        monkeypatch.setattr("app.cli.commands.deploy.generate", lambda m, d, **kw: good_code)
        monkeypatch.setattr(
            "app.cli.commands.deploy.build_deployment_spec",
            lambda facts: MagicMock(deployment_readiness="ready"),
        )

        write_called = {"called": False}

        def fake_write(*a, **kw):
            write_called["called"] = True

        monkeypatch.setattr("app.cli.core.writer.write_deployment", fake_write)

        # Must NOT call input() at all
        input_called = {"called": False}
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(
            AssertionError("input() should not be called with --yes")
        ))

        run_deploy(
            str(FIXTURE),
            name="sentiment", version="v99", device="cpu",
            routing="static", sample_input="this movie was great",
            yes=True,
        )

        assert write_called["called"]


# ===========================================================================
# Section 4: deploy --yes skips interpreter clarifying questions
# ===========================================================================


class TestDeployYesSkipsInterpreterQuestions:
    """With --yes, the interpreter auto-accepts the suggested_answer."""

    def test_yes_passes_interactive_false_to_interpret(self, monkeypatch):
        """--yes causes interpret() to be called with interactive=False."""
        from app.cli.commands.deploy import run_deploy
        from app.cli.core.agent import GeneratedCode
        from app.cli.core.inspector import ArtifactMetadata
        from app.cli.core.interpreter import InterpretationResult

        meta = ArtifactMetadata(
            framework="sklearn", class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint="raw text string", output_hint="integer class label",
            feature_count=None, class_labels=[0, 1],
            artifact_path=str(FIXTURE), artifact_size_mb=1.5,
        )

        good_load = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
        good_predict = "def predict(self, x):\n    return int(self._model.predict([x])[0])"
        good_code = GeneratedCode(load_body=good_load, predict_body=good_predict, raw="")

        monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p, **kw: meta)
        monkeypatch.setattr("app.cli.commands.deploy.generate", lambda m, d, **kw: good_code)
        monkeypatch.setattr(
            "app.cli.commands.deploy.build_deployment_spec",
            lambda facts: MagicMock(deployment_readiness="needs_interpretation"),
        )

        captured_interactive = {}

        def fake_interpret(m, s, *, sample_input, interactive):
            captured_interactive["value"] = interactive
            return InterpretationResult(
                framework="sklearn", load_format="joblib",
                input_hint="text", output_hint="int",
                confidence="high", suggested_sample_input="test input",
                question=None, question_field=None,
                options=None, suggested_answer=None,
            )

        monkeypatch.setattr("app.cli.commands.deploy.interpret", fake_interpret)
        monkeypatch.setattr("app.cli.commands.deploy.apply_interpretation", lambda m, r: m)
        monkeypatch.setattr("app.cli.core.writer.write_deployment", lambda *a, **kw: None)

        run_deploy(
            str(FIXTURE),
            name="sentiment", version="v99", device="cpu",
            routing="static", sample_input="great movie",
            yes=True,
        )

        assert captured_interactive["value"] is False


# ===========================================================================
# Section 5: fix --yes skips sample-input prompt
# ===========================================================================


class TestFixYesSkipsSampleInputPrompt:
    """With --yes and no --sample-input, fix uses suggested_sample_input or errors clearly."""

    def test_fix_yes_with_sample_input_skips_prompt(self, tmp_path, monkeypatch):
        """fix --yes --sample-input X skips the input() prompt."""
        from app.cli.commands.fix import run_fix

        definition = tmp_path / "definition.py"
        definition.write_text("class _GeneratedModel:\n    pass\n")

        # Make validate_pipeline succeed immediately
        monkeypatch.setattr(
            "app.cli.commands.fix.validate_pipeline",
            lambda src, inp, tmp: type("R", (), {"success": True, "output": 1, "error": None})(),
        )

        # input() must NOT be called
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(
            AssertionError("input() should not be called with --yes")
        ))

        run_fix(str(tmp_path), sample_input="hello world", yes=True)

    def test_fix_yes_without_sample_input_errors(self, tmp_path, monkeypatch):
        """fix --yes without --sample-input exits with error (no interactive fallback)."""
        from app.cli.commands.fix import run_fix

        definition = tmp_path / "definition.py"
        definition.write_text("class _GeneratedModel:\n    pass\n")

        with pytest.raises(SystemExit):
            run_fix(str(tmp_path), sample_input=None, yes=True)


# ===========================================================================
# Section 6: fix --yes skips write confirmation prompt
# ===========================================================================


class TestFixYesSkipsWriteConfirmation:
    """With --yes, fix writes the fixed file without asking."""

    def test_fix_yes_auto_writes(self, tmp_path, monkeypatch):
        """fix --yes writes the fixed definition without prompting."""
        from app.cli.commands.fix import run_fix
        from app.cli.core.agent import GeneratedCode

        good_load = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
        good_predict = "def predict(self, x):\n    return int(self._model.predict([x])[0])"

        # Write a broken definition
        from app.cli.core.inspector import ArtifactMetadata
        from app.cli.core.validator import build_definition_source

        bad_load = "def load(self) -> None:\n    raise RuntimeError('broken')"
        meta = ArtifactMetadata(
            framework="sklearn", class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint="raw text string", output_hint="integer class label",
            feature_count=None, class_labels=[0, 1],
            artifact_path=str(FIXTURE), artifact_size_mb=1.5,
        )
        broken_source = build_definition_source(meta, "sentiment", "v1", bad_load, good_predict)
        definition = tmp_path / "definition.py"
        definition.write_text(broken_source)

        good_code = GeneratedCode(load_body=good_load, predict_body=good_predict, raw="")
        monkeypatch.setattr("app.cli.commands.fix.llm_fix", lambda src, err: good_code)

        call_count = {"n": 0}

        def fake_validate(src, inp, tmp):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return type("R", (), {"success": False, "output": None, "error": "RuntimeError: broken"})()
            return type("R", (), {"success": True, "output": 1, "error": None})()

        monkeypatch.setattr("app.cli.commands.fix.validate_pipeline", fake_validate)

        # input() must NOT be called
        monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(
            AssertionError("input() should not be called with --yes")
        ))

        run_fix(str(tmp_path), sample_input="this movie was great", yes=True)

        # The file should have been written
        final_content = definition.read_text()
        assert "RuntimeError('broken')" not in final_content


# ===========================================================================
# Section 7: --yes wired through __main__.py correctly
# ===========================================================================


class TestMainWiresYesFlag:
    """__main__.py passes yes= to run_deploy and run_fix."""

    def test_main_passes_yes_to_deploy(self, monkeypatch):
        """main() passes yes=True to run_deploy when --yes is set."""
        from app.cli.__main__ import main

        captured = {}

        def fake_run_deploy(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("app.cli.commands.deploy.run_deploy", fake_run_deploy)
        monkeypatch.setattr(
            sys, "argv",
            ["inference-engine", "deploy", str(FIXTURE),
             "--name", "x", "--version", "v1",
             "--device", "cpu", "--routing", "static",
             "--sample-input", "test", "--yes"],
        )

        main()

        assert captured.get("yes") is True

    def test_main_passes_yes_to_fix(self, monkeypatch):
        """main() passes yes=True to run_fix when --yes is set."""
        from app.cli.__main__ import main

        captured = {}

        def fake_run_fix(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("app.cli.commands.fix.run_fix", fake_run_fix)
        monkeypatch.setattr(
            sys, "argv",
            ["inference-engine", "fix", "models/sentiment/v1/",
             "--sample-input", "test", "--yes"],
        )

        main()

        assert captured.get("yes") is True

    def test_main_defaults_yes_false_deploy(self, monkeypatch):
        """Without --yes, main() passes yes=False to run_deploy."""
        from app.cli.__main__ import main

        captured = {}

        def fake_run_deploy(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr("app.cli.commands.deploy.run_deploy", fake_run_deploy)
        monkeypatch.setattr(
            sys, "argv",
            ["inference-engine", "deploy", str(FIXTURE),
             "--name", "x", "--version", "v1",
             "--device", "cpu", "--routing", "static",
             "--sample-input", "test"],
        )

        main()

        assert captured.get("yes") is False


# ===========================================================================
# Section 8: Backward compatibility — without --yes, prompts still happen
# ===========================================================================


class TestBackwardCompatibility:
    """Without --yes, the existing behavior is preserved."""

    def test_deploy_still_prompts_without_yes(self, monkeypatch):
        """Without --yes in a TTY, deploy still prompts for deserialization."""
        from app.cli.commands.deploy import run_deploy

        monkeypatch.setattr("app.cli.commands.deploy._is_interactive", lambda: True)
        monkeypatch.setattr(
            "app.cli.commands.deploy.inspect_artifact",
            lambda p, **kw: MagicMock(
                framework="sklearn", class_name="Pipeline",
                class_hierarchy=[], input_hint="text", output_hint="int",
                feature_count=None, class_labels=None,
                artifact_path=str(FIXTURE), artifact_size_mb=1.0,
                raw_facts={}, extra={},
            ),
        )

        prompted = {"called": False}

        def fake_input(prompt=""):
            prompted["called"] = True
            return "n"  # Decline deserialization

        monkeypatch.setattr("builtins.input", fake_input)

        run_deploy(
            str(FIXTURE),
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            dry_run=True, yes=False,
        )

        assert prompted["called"]

    def test_fix_still_prompts_for_sample_input_without_yes(self, tmp_path, monkeypatch):
        """Without --yes in a TTY, fix prompts for sample_input if not provided."""
        from app.cli.commands.fix import run_fix

        definition = tmp_path / "definition.py"
        definition.write_text("class _GeneratedModel:\n    pass\n")

        monkeypatch.setattr("app.cli.commands.fix._is_interactive", lambda: True)
        monkeypatch.setattr(
            "app.cli.commands.fix.validate_pipeline",
            lambda src, inp, tmp: type("R", (), {"success": True, "output": 1, "error": None})(),
        )

        prompted = {"called": False}

        def fake_input(prompt=""):
            prompted["called"] = True
            return "this movie was great"

        monkeypatch.setattr("builtins.input", fake_input)

        run_fix(str(tmp_path), sample_input=None, yes=False)

        assert prompted["called"]


# ===========================================================================
# Section 9: --yes with collect_answers in prompts.py
# ===========================================================================


class TestCollectAnswersYes:
    """collect_answers() with yes=True skips prompts even if fields are missing."""

    def test_collect_answers_yes_all_provided(self):
        """With all fields + yes=True, returns answers immediately (no prompts)."""
        from app.cli.core.prompts import collect_answers

        result = collect_answers(
            str(FIXTURE),
            name="test", version="v1", device="cpu",
            routing="static", sample_input="hello",
            yes=True,
        )
        assert result.name == "test"
        assert result.version == "v1"

    def test_collect_answers_yes_missing_fields_exits(self):
        """With yes=True but missing core required fields (name/version/device/routing), exits with error."""
        from app.cli.core.prompts import collect_answers

        with pytest.raises(SystemExit):
            collect_answers(
                str(FIXTURE),
                name="test", version=None, device="cpu",
                routing=None, sample_input="hello",
                yes=True,
            )


# ===========================================================================
# Section 10: deploy --yes uses suggested_sample_input from interpretation
# ===========================================================================


class TestYesUsesSuggestedSampleInput:
    """When --yes is set and no --sample-input given, use interpretation's suggested_sample_input."""

    def test_yes_uses_suggested_sample_from_interpretation(self, monkeypatch):
        """--yes with missing --sample-input uses suggested_sample_input from interpretation."""
        from app.cli.commands.deploy import run_deploy
        from app.cli.core.agent import GeneratedCode
        from app.cli.core.inspector import ArtifactMetadata
        from app.cli.core.interpreter import InterpretationResult

        meta = ArtifactMetadata(
            framework="sklearn", class_name="Pipeline",
            class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
            input_hint="raw text string", output_hint="integer class label",
            feature_count=None, class_labels=[0, 1],
            artifact_path=str(FIXTURE), artifact_size_mb=1.5,
        )

        good_load = f"def load(self) -> None:\n    import joblib\n    self._model = joblib.load(r'{FIXTURE}')"
        good_predict = "def predict(self, x):\n    return int(self._model.predict([x])[0])"
        good_code = GeneratedCode(load_body=good_load, predict_body=good_predict, raw="")

        monkeypatch.setattr("app.cli.commands.deploy.inspect_artifact", lambda p, **kw: meta)
        monkeypatch.setattr("app.cli.commands.deploy.generate", lambda m, d, **kw: good_code)
        monkeypatch.setattr(
            "app.cli.commands.deploy.build_deployment_spec",
            lambda facts: MagicMock(deployment_readiness="needs_interpretation"),
        )

        interp = InterpretationResult(
            framework="sklearn", load_format="joblib",
            input_hint="text", output_hint="int",
            confidence="high", suggested_sample_input="the model works",
            question=None, question_field=None,
            options=None, suggested_answer=None,
        )
        monkeypatch.setattr("app.cli.commands.deploy.interpret", lambda m, s, **kw: interp)
        monkeypatch.setattr("app.cli.commands.deploy.apply_interpretation", lambda m, r: m)
        monkeypatch.setattr("app.cli.core.writer.write_deployment", lambda *a, **kw: None)

        # Pass all required fields EXCEPT sample_input
        # With --yes, should use suggested_sample_input from interpretation
        # This requires name/version/device/routing to be provided but sample_input
        # will be filled from the interpretation result
        run_deploy(
            str(FIXTURE),
            name="sentiment", version="v99", device="cpu",
            routing="static", sample_input=None,
            yes=True,
        )
        # If it didn't raise SystemExit, sample_input was resolved from interpretation
