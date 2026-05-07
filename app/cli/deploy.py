"""inference-engine deploy command — Phase 4: inspect + prompt + generate + validate + preview."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from app.cli.agent import GeneratedCode, fix, generate
from app.cli.inspector import ArtifactMetadata, inspect_artifact
from app.cli.prompts import DeployAnswers, _is_interactive, collect_answers, print_preview
from app.cli.validator import ValidationResult, build_definition_source, validate_pipeline

_PICKLE_WARNING = (
    "Warning: loading a pickle file executes arbitrary Python code.\n"
    "   Only load artifacts from sources you trust."
)

_MAX_RETRIES = 3


def _print_metadata(meta: ArtifactMetadata) -> None:
    print("\n[Inspector]")
    print(f"Detected: {meta.framework} / {meta.class_name}")
    if meta.class_hierarchy:
        print(f"  Pipeline: {' -> '.join(meta.class_hierarchy)}")
    print(f"  Input:  {meta.input_hint}")
    print(f"  Output: {meta.output_hint}")
    if meta.feature_count is not None:
        print(f"  Features: {meta.feature_count}")
    if meta.class_labels is not None:
        print(f"  Classes: {meta.class_labels}")
    print(f"  Artifact size: {meta.artifact_size_mb} MB")

    if meta.framework == "pytorch":
        print(
            "\nPyTorch models are not yet supported by the deploy command.\n"
            "Use the manual flow: docs/guides/adding-a-model.md"
        )


def _run_validation_loop(
    meta: ArtifactMetadata,
    answers: DeployAnswers,
    artifact_dest: str,
    code: GeneratedCode,
) -> GeneratedCode | None:
    """
    Validate the generated code against the sample input.
    Retry up to _MAX_RETRIES times, sending the traceback back to the LLM on failure.
    Returns the passing GeneratedCode, or None if all attempts fail.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        for attempt in range(1, _MAX_RETRIES + 1):
            source = build_definition_source(
                meta,
                name=answers.name,
                version=answers.version,
                load_body=code.load_body,
                predict_body=code.predict_body,
            )

            print(f"\n[Validation] Attempt {attempt}/{_MAX_RETRIES}...")
            result: ValidationResult = validate_pipeline(
                source, answers.sample_input, Path(tmp_dir)
            )

            if result.success:
                print(f"  Output: {result.output}")
                return code

            print(f"  Failed:\n{result.error}")

            if attempt < _MAX_RETRIES:
                print(f"[Retrying — sending error to LLM...]")
                try:
                    code = fix(code.raw, result.error)
                except Exception as e:
                    print(f"  LLM fix failed: {e}")
                    return None

    return None


def run_deploy(
    artifact_path: str,
    *,
    name: str | None = None,
    version: str | None = None,
    device: str | None = None,
    routing: str | None = None,
    sample_input: str | None = None,
) -> None:
    print(_PICKLE_WARNING)

    is_tty = _is_interactive()
    if is_tty:
        try:
            answer = input("   Continue? (Y/n) > ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("", "y", "yes"):
            print("Aborted.")
            sys.exit(0)
    else:
        print("   (Non-interactive mode -- proceeding automatically.)")

    try:
        meta = inspect_artifact(artifact_path)
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    _print_metadata(meta)

    if meta.framework == "pytorch":
        sys.exit(1)

    answers: DeployAnswers = collect_answers(
        artifact_path,
        name=name,
        version=version,
        device=device,
        routing=routing,
        sample_input=sample_input,
    )

    artifact_dest = f"models/{answers.name}/{answers.version}/{Path(artifact_path).name}"
    artifact_abs = str(Path(artifact_path).resolve())

    try:
        # Generate using the current (real) path so validation can load the file
        code: GeneratedCode = generate(meta, artifact_abs)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nError during code generation: {e}")
        sys.exit(1)

    print("\n[Generated code]")
    print(code.raw)

    passing_code = _run_validation_loop(meta, answers, artifact_abs, code)

    if passing_code is None:
        print(
            f"\nValidation failed after {_MAX_RETRIES} attempts. "
            "No files were written."
        )
        sys.exit(1)

    print_preview(answers, artifact_path)
