"""inference-engine deploy command — Phase 7: Rich output + --dry-run."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.cli.core.agent import GeneratedCode, fix, generate
from app.cli.core.inspector import ArtifactMetadata, inspect_artifact
from app.cli.core.interpreter import apply_interpretation, interpret
from app.cli.core.prompts import DeployAnswers, _is_interactive, collect_answers
from app.cli.core.spec_builder import build_deployment_spec
from app.cli.core.validator import ValidationResult, build_definition_source, validate_pipeline

console = Console()

_PICKLE_WARNING = (
    "[yellow]Warning:[/yellow] loading a pickle file executes arbitrary Python code.\n"
    "  Only load artifacts from sources you trust."
)

_MAX_RETRIES = 3


def _parse_sample_input(raw: str):
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _print_metadata(meta: ArtifactMetadata) -> None:
    table = Table(title="[bold]Inspector[/bold]", show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Framework", f"{meta.framework} / {meta.class_name}")
    if meta.class_hierarchy:
        table.add_row("Pipeline", " -> ".join(meta.class_hierarchy))
    table.add_row("Input", str(meta.input_hint))
    table.add_row("Output", str(meta.output_hint))
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
    with tempfile.TemporaryDirectory() as tmp_root:
        for attempt in range(1, _MAX_RETRIES + 1):
            tmp_dir = Path(tmp_root) / str(attempt)
            tmp_dir.mkdir()

            source = build_definition_source(
                meta,
                name=answers.name,
                version=answers.version,
                load_body=code.load_body,
                predict_body=code.predict_body,
            )

            with console.status(f"[cyan]Validating (attempt {attempt}/{_MAX_RETRIES})...[/cyan]"):
                result: ValidationResult = validate_pipeline(
                    source, _parse_sample_input(answers.sample_input), tmp_dir
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
    framework: str | None = None,
    allow_load: bool = False,
    yes: bool = False,
) -> None:
    console.print(_PICKLE_WARNING)

    is_tty = _is_interactive()
    if yes:
        # --yes implies allow_load and skips the deserialization prompt
        allow_load = True
    elif is_tty and not allow_load:
        try:
            answer = input("   Continue with deserialization? (Y/n) > ").strip().lower()
        except EOFError:
            answer = ""
        if answer in ("", "y", "yes"):
            allow_load = True
        else:
            console.print("  [dim](Proceeding without deserialization — metadata only.)[/dim]")
    elif not is_tty and not allow_load:
        console.print("  (Non-interactive mode without --allow-load — pickle deserialization skipped.)")

    with console.status("[cyan]Inspecting artifact...[/cyan]"):
        try:
            meta = inspect_artifact(artifact_path, framework_hint=framework, allow_load=allow_load)
        except FileNotFoundError:
            console.print(f"[red]Error:[/red] Artifact not found: {artifact_path}")
            sys.exit(1)
        except ValueError as e:
            console.print(f"[red]Error:[/red] Inspection failed: {e}")
            sys.exit(1)

    _print_metadata(meta)

    answers: DeployAnswers = collect_answers(
        artifact_path,
        name=name,
        version=version,
        device=device,
        routing=routing,
        sample_input=sample_input,
        allow_load=allow_load,
        yes=yes,
    )

    print_preview(answers, artifact_path, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        return

    artifact_abs = str(Path(artifact_path).resolve())

    # --- Stage 2: LLM interpretation (fires when metadata is incomplete) ---
    spec = build_deployment_spec(meta.raw_facts)
    if spec.deployment_readiness != "ready":
        with console.status("[cyan]Interpreting artifact metadata via LLM...[/cyan]"):
            interp_result = interpret(
                meta, spec,
                sample_input=answers.sample_input,
                interactive=is_tty and not yes,
            )
        if interp_result is not None:
            # --yes: use suggested_sample_input if no --sample-input was provided
            if yes and answers.sample_input is None and interp_result.suggested_sample_input:
                answers = DeployAnswers(
                    name=answers.name,
                    version=answers.version,
                    device=answers.device,
                    routing=answers.routing,
                    sample_input=interp_result.suggested_sample_input,
                    allow_load=answers.allow_load,
                )
            meta = apply_interpretation(meta, interp_result)
            console.print(
                f"  [green]Interpretation complete[/green] "
                f"(confidence: {interp_result.confidence})"
            )
    else:
        console.print("  [dim]Metadata complete — skipping interpretation.[/dim]")

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
            f"\n[yellow]Validation failed after {_MAX_RETRIES} attempts.[/yellow] "
            "Writing scaffold instead."
        )
        from app.cli.core.writer import write_scaffold
        write_scaffold(meta, answers, artifact_path)
        return

    if not yes and is_tty:
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
