"""File writer and routing patcher for the deploy command — Phase 5."""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

from app.cli.inspector import ArtifactMetadata
from app.cli.prompts import DeployAnswers
from app.cli.validator import build_definition_source

_ROUTING_PATH = Path("app/config/routing.py")


def _routing_entry(name: str, version: str, strategy: str) -> str:
    """Return the routing dict literal for the given strategy."""
    if strategy == "static":
        return (
            f'    "{name}": {{\n'
            f'        "strategy": "static",\n'
            f'        "version": "{version}",\n'
            f'    }},\n'
        )
    if strategy == "canary":
        return (
            f'    "{name}": {{\n'
            f'        "strategy": "canary",\n'
            f'        "primary": "{version}",\n'
            f'        "canary": "{version}",\n'
            f'        "canary_percent": 10,\n'
            f'    }},\n'
        )
    # ab
    return (
        f'    "{name}": {{\n'
        f'        "strategy": "ab",\n'
        f'        "variants": {{"{version}": 100}},\n'
        f'    }},\n'
    )


def _patch_routing(routing_path: Path, name: str, version: str, strategy: str) -> None:
    """
    Patch ROUTES in routing.py.
    - If the model name already exists, replace its entry (idempotent).
    - Otherwise append a new entry inside the ROUTES dict.
    Uses AST to locate the dict, then string surgery to insert/replace.
    """
    source = routing_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find the ROUTES assignment
    routes_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "ROUTES":
                    routes_node = node.value
                    break

    if routes_node is None:
        raise ValueError("Could not find ROUTES dict in routing.py")

    new_entry = _routing_entry(name, version, strategy)

    # Check if the model name already exists as a key
    existing_key_node = None
    for knode in routes_node.keys:
        if isinstance(knode, ast.Constant) and knode.value == name:
            existing_key_node = knode
            break

    lines = source.splitlines(keepends=True)

    if existing_key_node is not None:
        # Find the corresponding value node to determine the span to replace
        idx = routes_node.keys.index(existing_key_node)
        val_node = routes_node.values[idx]

        # The entry spans from the key line to the end of the value node
        key_line = existing_key_node.lineno - 1   # 0-indexed
        val_end_line = val_node.end_lineno         # 1-indexed, inclusive

        # Walk back from val_end_line to include the trailing comma/newline
        end_idx = val_end_line  # 0-indexed exclusive = val_end_line
        # Include a trailing comma line if present
        if end_idx < len(lines) and lines[end_idx].strip() in (",", "},"):
            end_idx += 1

        print(f"  (Replacing existing routing entry for {name!r})")
        lines[key_line:end_idx] = [new_entry]
    else:
        # Append before the closing brace of ROUTES
        close_line = routes_node.end_lineno - 1  # 0-indexed
        lines.insert(close_line, new_entry)

    routing_path.write_text("".join(lines), encoding="utf-8")

    # Verify the result is valid Python
    try:
        ast.parse("".join(lines))
    except SyntaxError as e:
        raise ValueError(f"routing.py is invalid after patch: {e}") from e


def write_deployment(
    meta: ArtifactMetadata,
    answers: DeployAnswers,
    artifact_path: str,
    load_body: str,
    predict_body: str,
    *,
    models_root: str = "models",
    routing_path: Path = _ROUTING_PATH,
) -> None:
    """
    Write all deployment files:
    1. mkdir models/<name>/<version>/
    2. Copy artifact
    3. Write definition.py
    4. Patch app/config/routing.py
    5. Print the test curl command
    """
    dest_dir = Path(models_root) / answers.name / answers.version
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy artifact
    artifact_filename = Path(artifact_path).name
    dest_artifact = dest_dir / artifact_filename
    shutil.copy2(artifact_path, dest_artifact)

    # Write definition.py — use the dest path so the deployed model loads from models/
    artifact_dest = str(dest_artifact)
    source = build_definition_source(
        meta,
        name=answers.name,
        version=answers.version,
        load_body=load_body,
        predict_body=predict_body,
    )
    # Replace the absolute validation path with the relative deployment path
    source = source.replace(repr(str(Path(artifact_path).resolve())), repr(artifact_dest))

    definition_path = dest_dir / "definition.py"
    definition_path.write_text(source, encoding="utf-8")

    # Patch routing.py
    _patch_routing(routing_path, answers.name, answers.version, answers.routing)

    print(f"\nDone. Written:")
    print(f"  {dest_dir}/definition.py")
    print(f"  {dest_dir}/{artifact_filename}")
    print(f"  {routing_path}  [patched]")
    print(f"\nRestart the server to load the model.")
    print(f"\nTest it:")
    print(
        f"  curl -X POST http://localhost:8000/predict \\\n"
        f"    -H \"X-API-Key: dev-key\" \\\n"
        f"    -H \"Content-Type: application/json\" \\\n"
        f"    -d '{{\"model\": \"{answers.name}\", \"version\": \"{answers.version}\", "
        f"\"data\": {answers.sample_input!r}}}'"
    )
