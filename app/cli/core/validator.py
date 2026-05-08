"""Validation loop for generated load() and predict() — Phase 4."""
from __future__ import annotations

import importlib.util
import sys
import textwrap
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.cli.core.inspector import ArtifactMetadata

# Template that wraps the two generated method bodies into a full definition.py
_DEFINITION_TEMPLATE = """\
from app.domain.models.base import BaseModel
from app.domain.processing.pre import IdentityPreprocessor
from app.domain.processing.post import IdentityPostprocessor
from app.domain.pipelines.base import InferencePipeline

MODEL_NAME = {name!r}
MODEL_VERSION = {version!r}

class _GeneratedModel(BaseModel):
{load_body}

{predict_body}

def build_pipeline() -> InferencePipeline:
    model = _GeneratedModel()
    model.load()
    return InferencePipeline(
        preprocessor=IdentityPreprocessor(),
        model=model,
        postprocessor=IdentityPostprocessor(),
    )
"""


@dataclass
class ValidationResult:
    success: bool
    output: Any = None
    error: str | None = None


def _indent(code: str, spaces: int = 4) -> str:
    """Indent every line of code by `spaces` spaces."""
    return textwrap.indent(code, " " * spaces)


def build_definition_source(
    meta: ArtifactMetadata,
    name: str,
    version: str,
    load_body: str,
    predict_body: str,
) -> str:
    """Render the full definition.py source from the two generated method bodies."""
    return _DEFINITION_TEMPLATE.format(
        name=name,
        version=version,
        load_body=_indent(load_body),
        predict_body=_indent(predict_body),
    )


def validate_pipeline(
    source: str,
    sample_input: Any,
    tmp_dir: Path,
) -> ValidationResult:
    """
    Write `source` to a temp file, import it, call build_pipeline(),
    run pipeline.run(sample_input), and return the result or error.
    """
    definition_path = tmp_dir / "definition.py"
    definition_path.write_text(source, encoding="utf-8")

    # Ensure the temp dir is importable
    tmp_str = str(tmp_dir)
    inserted = tmp_str not in sys.path
    if inserted:
        sys.path.insert(0, tmp_str)

    # Remove any cached version of the module
    mod_name = "definition"
    sys.modules.pop(mod_name, None)

    try:
        spec = importlib.util.spec_from_file_location(mod_name, definition_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pipeline = mod.build_pipeline()
        output = pipeline.run(sample_input)
        return ValidationResult(success=True, output=output)
    except Exception:
        return ValidationResult(success=False, error=traceback.format_exc())
    finally:
        sys.modules.pop(mod_name, None)
        if inserted:
            sys.path.remove(tmp_str)
