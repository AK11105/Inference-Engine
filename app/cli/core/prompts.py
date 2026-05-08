"""Interactive prompt session for the deploy command (Phase 2)."""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


def _is_interactive() -> bool:
    """Return True only when running in a real interactive terminal."""
    try:
        return sys.stdin.isatty() and os.isatty(sys.stdin.fileno())
    except Exception:
        return False


@dataclass
class DeployAnswers:
    name: str
    version: str
    device: str
    routing: str
    sample_input: str


def _next_version(name: str, models_root: str = "models") -> str:
    """Return the next auto-incremented version for a model name."""
    model_dir = Path(models_root) / name
    if not model_dir.exists():
        return "v1"
    existing = sorted(
        d.name for d in model_dir.iterdir()
        if d.is_dir() and re.fullmatch(r"v\d+", d.name)
    )
    if not existing:
        return "v1"
    last_num = int(existing[-1][1:])
    return f"v{last_num + 1}"


def _derive_name(artifact_path: str) -> str:
    """Derive a model name from the artifact filename."""
    stem = Path(artifact_path).stem
    stem = re.sub(r"[_-](model|clf|pipeline|classifier|regressor)$", "", stem, flags=re.IGNORECASE)
    return stem.lower()


def _exit_missing(name, version, device, routing, sample_input) -> None:
    missing = [
        flag
        for flag, val in [
            ("--name", name),
            ("--version", version),
            ("--device", device),
            ("--routing", routing),
            ("--sample-input", sample_input),
        ]
        if val is None
    ]
    print(
        f"Error: non-interactive mode requires all flags to be set.\n"
        f"Missing: {', '.join(missing)}"
    )
    sys.exit(1)


def collect_answers(
    artifact_path: str,
    *,
    name: str | None = None,
    version: str | None = None,
    device: str | None = None,
    routing: str | None = None,
    sample_input: str | None = None,
    models_root: str = "models",
) -> DeployAnswers:
    """
    Collect deployment parameters either from CLI flags (non-interactive)
    or via questionary prompts (interactive TTY).

    When all five values are provided via flags, no prompts are shown.
    When running in a non-TTY and any value is missing, exits with an error.
    """
    all_provided = all(v is not None for v in (name, version, device, routing, sample_input))

    if all_provided:
        return DeployAnswers(
            name=name,
            version=version,
            device=device,
            routing=routing,
            sample_input=sample_input,
        )

    if not _is_interactive():
        _exit_missing(name, version, device, routing, sample_input)

    import questionary

    derived_name = name or _derive_name(artifact_path)

    try:
        resolved_name = questionary.text("Model name:", default=derived_name).ask()
        if resolved_name is None:
            sys.exit(0)
        resolved_name = resolved_name.strip() or derived_name

        auto_ver = _next_version(resolved_name, models_root)
        resolved_version = version
        if resolved_version is None:
            resolved_version = questionary.text(
                f"Version (auto: {auto_ver}):", default=auto_ver
            ).ask()
            if resolved_version is None:
                sys.exit(0)
            resolved_version = resolved_version.strip() or auto_ver

        resolved_device = device
        if resolved_device is None:
            resolved_device = questionary.select(
                "Execution target:", choices=["cpu", "gpu"], default="cpu"
            ).ask()
            if resolved_device is None:
                sys.exit(0)

        resolved_routing = routing
        if resolved_routing is None:
            resolved_routing = questionary.select(
                "Routing strategy:", choices=["static", "canary", "ab"], default="static"
            ).ask()
            if resolved_routing is None:
                sys.exit(0)

        resolved_sample = sample_input
        if resolved_sample is None:
            resolved_sample = questionary.text("Sample input for validation:").ask()
            if resolved_sample is None:
                sys.exit(0)

    except Exception:
        # prompt_toolkit can't render (e.g. no Windows console in subprocess) — non-interactive
        _exit_missing(name, version, device, routing, sample_input)

    return DeployAnswers(
        name=resolved_name,
        version=resolved_version,
        device=resolved_device,
        routing=resolved_routing,
        sample_input=resolved_sample,
    )


def print_preview(answers: DeployAnswers, artifact_path: str) -> None:
    """Print the files that would be written."""
    artifact_filename = Path(artifact_path).name
    dest_dir = f"models/{answers.name}/{answers.version}"
    print("\n[Preview]")
    print(f"  {dest_dir}/definition.py          [new]")
    print(f"  {dest_dir}/{artifact_filename}    [copied]")
    print(f"  app/config/routing.py              [patched]")
    print(f"\n  Model:   {answers.name}:{answers.version}")
    print(f"  Device:  {answers.device}")
    print(f"  Routing: {answers.routing}")
