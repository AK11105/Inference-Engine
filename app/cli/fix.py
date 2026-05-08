"""Fix command — reads an existing definition.py, validates it, and proposes an LLM fix."""
from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

from app.cli.agent import fix as llm_fix
from app.cli.prompts import _is_interactive
from app.cli.validator import validate_pipeline

_MAX_RETRIES = 3


def run_fix(model_dir: str) -> None:
    definition_path = Path(model_dir) / "definition.py"
    if not definition_path.exists():
        print(f"Error: {definition_path} not found.")
        sys.exit(1)

    original_source = definition_path.read_text(encoding="utf-8")

    # Extract sample input from the user (required for validation)
    if _is_interactive():
        try:
            sample_input = input("Sample input for validation: ").strip()
        except EOFError:
            print("Error: --sample-input required in non-interactive mode.")
            sys.exit(1)
    else:
        print("Error: sample input required. Use interactive mode or provide it when prompted.")
        sys.exit(1)

    print("\n[Validation] Checking existing pipeline...")
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = validate_pipeline(original_source, sample_input, Path(tmp_dir))

    if result.success:
        print(f"  Pipeline is valid. Output: {result.output}")
        print("Nothing to fix.")
        return

    print(f"  Failed:\n{result.error}")

    # Retry loop
    current_source = original_source
    fixed_source: str | None = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        for attempt in range(1, _MAX_RETRIES + 1):
            print(f"\n[Fix] Attempt {attempt}/{_MAX_RETRIES} — sending error to LLM...")
            try:
                code = llm_fix(current_source, result.error)
            except Exception as e:
                print(f"  LLM call failed: {e}")
                break

            # Rebuild source with fixed methods
            new_source = _splice_methods(current_source, code.load_body, code.predict_body)

            print(f"[Validation] Attempt {attempt}/{_MAX_RETRIES}...")
            result = validate_pipeline(new_source, sample_input, Path(tmp_dir))

            if result.success:
                print(f"  Output: {result.output}")
                fixed_source = new_source
                break

            print(f"  Failed:\n{result.error}")
            current_source = new_source

    if fixed_source is None:
        print(f"\nFix failed after {_MAX_RETRIES} attempts. No files written.")
        sys.exit(1)

    # Show diff
    diff = difflib.unified_diff(
        original_source.splitlines(keepends=True),
        fixed_source.splitlines(keepends=True),
        fromfile=f"{definition_path} (original)",
        tofile=f"{definition_path} (fixed)",
    )
    print("\n[Diff]")
    print("".join(diff) or "  (no changes)")

    if _is_interactive():
        try:
            confirm = input("\n? Write fixed file? (Y/n) > ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("", "y", "yes"):
            print("Aborted. No files written.")
            return

    definition_path.write_text(fixed_source, encoding="utf-8")
    print(f"\nDone. Written: {definition_path}")


def _splice_methods(source: str, load_body: str, predict_body: str) -> str:
    """Replace the load() and predict() method bodies in an existing definition source."""
    import re, textwrap

    def _indent(code: str, spaces: int = 4) -> str:
        return textwrap.indent(code, " " * spaces)

    source = re.sub(
        r"(    def load\(self\).*?)(?=\n    def |\ndef |\Z)",
        lambda m: "    " + load_body.strip(),
        source,
        count=1,
        flags=re.DOTALL,
    )
    source = re.sub(
        r"(    def predict\(self,.*?)(?=\n    def |\ndef |\Z)",
        lambda m: "    " + predict_body.strip(),
        source,
        count=1,
        flags=re.DOTALL,
    )
    return source
