"""inference-engine deploy command — Phase 7: Rich output + --dry-run."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

from rich.console import Console
from rich.table import Table

from app.cli.core.agent import GeneratedCode, fix, generate
from app.cli.core.inspector import ArtifactMetadata, inspect_artifact
from app.cli.core.interpreter import _DEFAULT_MODEL as _INTERPRETER_DEFAULT_MODEL
from app.cli.core.interpreter import apply_interpretation, interpret
from app.cli.core.prompts import DeployAnswers, _is_interactive, collect_answers
from app.cli.core.spec_builder import build_deployment_spec
from app.cli.core.validator import ValidationResult, build_definition_source, validate_pipeline
from app.core import context
from app.core.logging import get_logger

console = Console()
logger = get_logger(__name__)
_COMPONENT = "DeploymentCLI"

_PICKLE_WARNING = (
    "[yellow]Warning:[/yellow] loading a pickle file executes arbitrary Python code.\n"
    "  Only load artifacts from sources you trust."
)

_MAX_RETRIES = 3


def _parse_sample_input(raw: str):
    from app.cli.core.sample_input import parse_sample_input
    return parse_sample_input(raw)


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
    deployment_id: str | None = None,
) -> GeneratedCode | None:
    logger.info(event="ValidationStarted", component=_COMPONENT, deployment_id=deployment_id)
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
                logger.info(
                    event="ValidationPassed", component=_COMPONENT, deployment_id=deployment_id,
                    sample_output_preview=str(result.output)[:200],
                )
                return code

            console.print(f"  [red]Validation failed (attempt {attempt}/{_MAX_RETRIES}).[/red]")
            console.print(f"  [dim]{result.error}[/dim]")
            logger.warning(
                event="ValidationFailed", component=_COMPONENT, deployment_id=deployment_id,
                error=result.error, error_type=result.error_type,
            )

            if attempt < _MAX_RETRIES:
                try:
                    with console.status("[cyan]Sending error to LLM for fix...[/cyan]"):
                        code = fix(code.raw, result.error, sample_input=answers.sample_input, meta=meta)
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
    # Single one-shot CLI invocation per process — no reset needed.
    deployment_id = str(uuid.uuid4())
    context.set_correlation_context(deployment_id=deployment_id)
    deploy_start = time.time()
    logger.info(
        event="DeploymentStarted", component=_COMPONENT, deployment_id=deployment_id,
        artifact_path=artifact_path, device=device, routing=routing,
    )

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
        except FileNotFoundError as e:
            console.print(f"[red]Error:[/red] Artifact not found: {artifact_path}")
            logger.error(
                event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
                stage="inspection", error=str(e), error_type=type(e).__name__,
            )
            sys.exit(1)
        except ValueError as e:
            console.print(f"[red]Error:[/red] Inspection failed: {e}")
            logger.error(
                event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
                stage="inspection", error=str(e), error_type=type(e).__name__,
            )
            sys.exit(1)

    logger.info(
        event="ArtifactInspectionCompleted", component=_COMPONENT, deployment_id=deployment_id,
        artifact_type=meta.raw_facts.get("format"), file_size_bytes=os.path.getsize(artifact_path),
    )

    _print_metadata(meta)

    try:
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
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(
            event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
            stage="answers", error=str(e), error_type=type(e).__name__,
        )
        sys.exit(1)
    logger.info(
        event="DeploymentConfigurationLoaded", component=_COMPONENT, deployment_id=deployment_id,
        model_name=answers.name, version=answers.version,
    )

    print_preview(answers, artifact_path, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        return

    artifact_abs = str(Path(artifact_path).resolve())

    # --- Stage 2: LLM interpretation (fires when metadata is incomplete) ---
    spec = build_deployment_spec(meta.raw_facts)
    if spec.deployment_readiness != "ready":
        interp_start = time.time()
        with console.status("[cyan]Interpreting artifact metadata via LLM...[/cyan]"):
            interp_result = interpret(
                meta, spec,
                sample_input=answers.sample_input,
                interactive=is_tty and not yes,
            )
        if interp_result is not None:
            logger.info(
                event="LLMInterpretationCompleted", component=_COMPONENT, deployment_id=deployment_id,
                llm_model=os.environ.get("INFERENCE_ENGINE_LLM_MODEL", _INTERPRETER_DEFAULT_MODEL),
                latency_ms=(time.time() - interp_start) * 1000,
            )
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

    codegen_start = time.time()
    try:
        with console.status(f"[cyan]Generating load() and predict() via LLM...[/cyan]"):
            code: GeneratedCode = generate(meta, artifact_abs, sample_input=answers.sample_input)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[red]Error during code generation:[/red] {e}")
        logger.error(
            event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
            stage="codegen", error=str(e), error_type=type(e).__name__,
        )
        sys.exit(1)
    logger.info(
        event="CodeGenerationCompleted", component=_COMPONENT, deployment_id=deployment_id,
        latency_ms=(time.time() - codegen_start) * 1000,
    )

    console.print("\n[bold]Generated code:[/bold]")
    console.print(code.raw)

    passing_code = _run_validation_loop(meta, answers, artifact_abs, code, deployment_id)

    if passing_code is None:
        console.print(
            f"\n[yellow]Validation failed after {_MAX_RETRIES} attempts.[/yellow] "
            "Writing scaffold instead."
        )
        logger.warning(
            event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
            stage="validation", error="validation failed after max retries", error_type="ValidationExhausted",
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
        logger.error(
            event="DeploymentFailed", component=_COMPONENT, deployment_id=deployment_id,
            stage="write", error=str(e), error_type=type(e).__name__,
        )
        sys.exit(1)

    definition_path = f"models/{answers.name}/{answers.version}/definition.py"
    logger.info(
        event="DeploymentCompleted", component=_COMPONENT, deployment_id=deployment_id,
        model=answers.name, version=answers.version, definition_path=definition_path,
        total_latency_ms=(time.time() - deploy_start) * 1000,
    )
