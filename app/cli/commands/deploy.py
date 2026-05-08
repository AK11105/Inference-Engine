"""inference-engine deploy command — Phase 7: Rich output + --dry-run."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.cli.core.agent import GeneratedCode, fix, generate
from app.cli.core.inspector import ArtifactMetadata, inspect_artifact
from app.cli.core.prompts import DeployAnswers, _is_interactive, collect_answers
from app.cli.core.validator import ValidationResult, build_definition_source, validate_pipeline

console = Console()

_PICKLE_WARNING = (
    "[yellow]Warning:[/yellow] loading a pickle file executes arbitrary Python code.\n"
    "  Only load artifacts from sources you trust."
)

_MAX_RETRIES = 3


def _print_metadata(meta: ArtifactMetadata) -> None:
    table = Table(title="[bold]Inspector[/bold]", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Framework", f"{meta.framework} / {meta.class_name}")
    if meta.class_hierarchy:
        table.add_row("Pipeline", " -> ".join(meta.class_hierarchy))
    table.add_row("Input", meta.input_hint)
    table.add_row("Output", meta.output_hint)
    if meta.feature_count is not None:
        table.add_row("Features", str(meta.feature_count))
    if meta.class_labels is not None:
        table.add_row("Classes", str(meta.class_labels))
    table.add_row("Size", f"{meta.artifact_size_mb} MB")
    console.print(table)


def print_preview(answers: DeployAnswers, artifact_path: str, dry_run: bool = False) -> None:
    artifact_filename = Path(artifact_path).name
    dest_dir = f"models/{answers.name}/{answers.version}"
    tag = "[dim](dry run — not written)[/dim]" if dry_run else "[green][new][/green]"

    table = Table(title="[bold]Preview[/bold]", show_header=False, box=None, padding=(0, 2))
    table.add_column()
    table.add_column()
    table.add_row(f"{dest_dir}/definition.py", tag)
    table.add_row(f"{dest_dir}/{artifact_filename}", tag)
    table.add_row("app/config/routing.py", "[dim](dry run — not patched)[/dim]" if dry_run else "[green][patched][/green]")
    table.add_row("Model", f"{answers.name}:{answers.version}")
    table.add_row("Device", answers.device)
    table.add_row("Routing", answers.routing)
    console.print(table)


def _run_validation_loop(
    meta: ArtifactMetadata,
    answers: DeployAnswers,
    artifact_dest: str,
    code: GeneratedCode,
) -> GeneratedCode | None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        for attempt in range(1, _MAX_RETRIES + 1):
            source = build_definition_source(
                meta,
                name=answers.name,
                version=answers.version,
                load_body=code.load_body,
                predict_body=code.predict_body,
            )

            with console.status(f"[cyan]Validating (attempt {attempt}/{_MAX_RETRIES})...[/cyan]"):
                result: ValidationResult = validate_pipeline(
                    source, answers.sample_input, Path(tmp_dir)
                )

            if result.success:
                console.print(f"  [green]Validation passed.[/green] Output: {result.output}")
                return code

            console.print(f"  [red]Validation failed (attempt {attempt}/{_MAX_RETRIES}).[/red]")
            console.print(f"  [dim]{result.error}[/dim]")

            if attempt < _MAX_RETRIES:
                try:
                    with console.status("[cyan]Sending error to LLM for fix...[/cyan]"):
                        code = fix(code.raw, result.error)
                except Exception as e:
                    console.print(f"  [red]LLM fix failed:[/red] {e}")
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
    dry_run: bool = False,
) -> None:
    console.print(_PICKLE_WARNING)

    is_tty = _is_interactive()
    if is_tty:
        try:
            answer = input("   Continue? (Y/n) > ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("", "y", "yes"):
            console.print("Aborted.")
            sys.exit(0)
    else:
        console.print("  [dim](Non-interactive mode — proceeding automatically.)[/dim]")

    with console.status("[cyan]Inspecting artifact...[/cyan]"):
        try:
            meta = inspect_artifact(artifact_path)
        except FileNotFoundError:
            console.print(f"[red]Error:[/red] Artifact not found: {artifact_path}")
            sys.exit(1)
        except ValueError as e:
            console.print(f"[red]Error:[/red] Inspection failed: {e}")
            sys.exit(1)

    _print_metadata(meta)

    if meta.framework == "pytorch":
        console.print(
            "[yellow]PyTorch models are not yet supported.[/yellow]\n"
            "Use the manual flow: docs/guides/adding-a-model.md"
        )
        sys.exit(1)

    answers: DeployAnswers = collect_answers(
        artifact_path,
        name=name,
        version=version,
        device=device,
        routing=routing,
        sample_input=sample_input,
    )

    artifact_abs = str(Path(artifact_path).resolve())

    try:
        with console.status(f"[cyan]Generating load() and predict() via LLM...[/cyan]"):
            code: GeneratedCode = generate(meta, artifact_abs)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]Error during code generation:[/red] {e}")
        sys.exit(1)

    console.print("\n[bold]Generated code:[/bold]")
    console.print(code.raw)

    passing_code = _run_validation_loop(meta, answers, artifact_abs, code)

    if passing_code is None:
        console.print(
            f"\n[red]Validation failed after {_MAX_RETRIES} attempts.[/red] "
            "No files were written."
        )
        sys.exit(1)

    print_preview(answers, artifact_path, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        return

    if is_tty:
        try:
            confirm = input("\n? Write these files? (Y/n) > ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("", "y", "yes"):
            console.print("Aborted. No files written.")
            sys.exit(0)

    from app.cli.core.writer import write_deployment
    try:
        write_deployment(
            meta,
            answers,
            artifact_path,
            load_body=passing_code.load_body,
            predict_body=passing_code.predict_body,
        )
    except Exception as e:
        console.print(f"[red]Error writing files:[/red] {e}")
        sys.exit(1)
