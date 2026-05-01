"""inference-engine deploy command -- Phase 1: inspect and print metadata."""
from __future__ import annotations

import sys

from app.cli.inspector import ArtifactMetadata, inspect_artifact

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


def run_deploy(artifact_path: str) -> None:
    """Entry point for the deploy command (Phase 1: inspect only)."""
    print(_PICKLE_WARNING)

    is_tty = sys.stdin.isatty()
    if is_tty:
        answer = input("   Continue? (Y/n) > ").strip().lower()
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
