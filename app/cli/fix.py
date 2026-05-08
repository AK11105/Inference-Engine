"""Fix command — Phase 7: Rich output."""
from __future__ import annotations

import difflib
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.syntax import Syntax

from app.cli.agent import fix as llm_fix
from app.cli.prompts import _is_interactive
from app.cli.validator import validate_pipeline

console = Console()
_MAX_RETRIES = 3


def run_fix(model_dir: str) -> None:
    definition_path = Path(model_dir) / "definition.py"
    if not definition_path.exists():
        console.print(f"[red]Error:[/red] {definition_path} not found.")
        sys.exit(1)

    original_source = definition_path.read_text(encoding="utf-8")

    if _is_interactive():
        try:
            sample_input = input("Sample input for validation: ").strip()
        except EOFError:
            console.print("[red]Error:[/red] sample input required in non-interactive mode.")
            sys.exit(1)
    else:
        console.print("[red]Error:[/red] sample input required. Run in an interactive terminal.")
        sys.exit(1)

    with console.status("[cyan]Validating existing pipeline...[/cyan]"):
        result = validate_pipeline(original_source, sample_input, Path(tempfile.mkdtemp()))

    if result.success:
        console.print(f"  [green]Pipeline is valid.[/green] Output: {result.output}")
        console.print("Nothing to fix.")
        return

    console.print(f"  [red]Validation failed.[/red]")
    console.print(f"  [dim]{result.error}[/dim]")

    current_source = original_source
    fixed_source: str | None = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with console.status(f"[cyan]Fix attempt {attempt}/{_MAX_RETRIES} — calling LLM...[/cyan]"):
                    code = llm_fix(current_source, result.error)
            except Exception as e:
                console.print(f"  [red]LLM call failed:[/red] {e}")
                break

            new_source = _splice_methods(current_source, code.load_body, code.predict_body)

            with console.status(f"[cyan]Validating fix {attempt}/{_MAX_RETRIES}...[/cyan]"):
                result = validate_pipeline(new_source, sample_input, Path(tmp_dir))

            if result.success:
                console.print(f"  [green]Fix validated.[/green] Output: {result.output}")
                fixed_source = new_source
                break

            console.print(f"  [red]Still failing (attempt {attempt}/{_MAX_RETRIES}).[/red]")
            console.print(f"  [dim]{result.error}[/dim]")
            current_source = new_source

    if fixed_source is None:
        console.print(f"\n[red]Fix failed after {_MAX_RETRIES} attempts. No files written.[/red]")
        sys.exit(1)

    diff = "".join(difflib.unified_diff(
        original_source.splitlines(keepends=True),
        fixed_source.splitlines(keepends=True),
        fromfile=f"{definition_path} (original)",
        tofile=f"{definition_path} (fixed)",
    ))
    console.print("\n[bold]Diff:[/bold]")
    if diff:
        console.print(Syntax(diff, "diff", theme="ansi_dark"))
    else:
        console.print("  (no changes)")

    if _is_interactive():
        try:
            confirm = input("\n? Write fixed file? (Y/n) > ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("", "y", "yes"):
            console.print("Aborted. No files written.")
            return

    definition_path.write_text(fixed_source, encoding="utf-8")
    console.print(f"\n[green]Done.[/green] Written: {definition_path}")


def _splice_methods(source: str, load_body: str, predict_body: str) -> str:
    import re
    source = re.sub(
        r"(    def load\(self\).*?)(?=\n    def |\ndef |\Z)",
        lambda m: "    " + load_body.strip(),
        source, count=1, flags=re.DOTALL,
    )
    source = re.sub(
        r"(    def predict\(self,.*?)(?=\n    def |\ndef |\Z)",
        lambda m: "    " + predict_body.strip(),
        source, count=1, flags=re.DOTALL,
    )
    return source
