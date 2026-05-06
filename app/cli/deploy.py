"""inference-engine deploy command — Phase 3: inspect + prompt + generate + preview."""
from __future__ import annotations

import sys
from pathlib import Path

from app.cli.agent import GeneratedCode, generate
from app.cli.inspector import ArtifactMetadata, inspect_artifact
from app.cli.prompts import DeployAnswers, _is_interactive, collect_answers, print_preview

_PICKLE_WARNING = (
    "Warning: loading a pickle file executes arbitrary Python code.\n"
    "   Only load artifacts from sources you trust."
)


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


def run_deploy(
    artifact_path: str,
    *,
    name: str | None = None,
    version: str | None = None,
    device: str | None = None,
    routing: str | None = None,
    sample_input: str | None = None,
) -> None:
    """Entry point for the deploy command (Phase 2: inspect + prompt + preview)."""
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

    try:
        code: GeneratedCode = generate(meta, artifact_dest)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nError during code generation: {e}")
        sys.exit(1)

    print("\n[Generated code]")
    print(code.raw)

    print_preview(answers, artifact_path)
