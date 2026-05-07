"""LLM code generation for load() and predict() via Groq — Phase 3."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from app.cli.inspector import ArtifactMetadata

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore[assignment,misc]

_DEFAULT_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """\
You are generating two Python method bodies for an ML inference engine.
You only write load() and predict().

Rules:
- load() must assign the loaded model to self._model
- predict() receives a single input x and returns a single output
- No imports inside methods unless absolutely necessary
- No print statements
- Return ONLY the two method bodies as plain Python, no class wrapper, no markdown fences
- Use exactly these signatures:
    def load(self) -> None:
    def predict(self, x):
"""


def _build_user_prompt(meta: ArtifactMetadata, artifact_dest: str) -> str:
    lines = [
        f"Artifact: {meta.framework} {meta.class_name}",
    ]
    if meta.class_hierarchy:
        lines.append(f"Pipeline steps: {' -> '.join(meta.class_hierarchy)}")
    lines.append(f"Input: {meta.input_hint}")
    lines.append(f"Output: {meta.output_hint}")
    if meta.feature_count is not None:
        lines.append(f"Feature count: {meta.feature_count}")
    if meta.class_labels is not None:
        lines.append(f"Classes: {meta.class_labels}")
    lines.append(f"Artifact path (at runtime): {artifact_dest}")
    lines.append("")
    lines.append("Write load() and predict().")
    return "\n".join(lines)


def _check_api_key() -> None:
    if not os.environ.get("GROQ_API_KEY"):
        raise SystemExit(
            "Error: GROQ_API_KEY is not set.\n"
            "Set it with: export GROQ_API_KEY=<your-key>"
        )


def _parse_methods(raw: str) -> tuple[str, str]:
    """Extract load() and predict() bodies from raw LLM output."""
    # Strip markdown fences if the model added them anyway
    raw = re.sub(r"```(?:python)?", "", raw).replace("```", "").strip()

    load_match = re.search(r"(def load\(self\).*?)(?=\ndef |\Z)", raw, re.DOTALL)
    predict_match = re.search(r"(def predict\(self,.*?)(?=\ndef |\Z)", raw, re.DOTALL)

    if not load_match or not predict_match:
        raise ValueError(
            f"Could not parse load() and predict() from LLM output:\n{raw}"
        )

    return load_match.group(1).strip(), predict_match.group(1).strip()


@dataclass
class GeneratedCode:
    load_body: str
    predict_body: str
    raw: str


def fix(
    previous_code: str,
    error: str,
    *,
    model: str | None = None,
) -> GeneratedCode:
    """Ask the LLM to fix previously generated code given a traceback."""
    _check_api_key()

    if Groq is None:
        raise SystemExit("Error: groq package not installed.\nInstall with: pip install groq")

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    chosen_model = model or os.environ.get("INFERENCE_ENGINE_LLM_MODEL", _DEFAULT_MODEL)

    user_prompt = (
        f"The following code failed with this error:\n\n"
        f"```\n{error}\n```\n\n"
        f"Here is the code that failed:\n\n"
        f"```python\n{previous_code}\n```\n\n"
        f"Fix load() and predict() so the error is resolved. "
        f"Return only the two corrected method bodies."
    )

    response = client.chat.completions.create(
        model=chosen_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = response.choices[0].message.content.strip()
    load_body, predict_body = _parse_methods(raw)
    return GeneratedCode(load_body=load_body, predict_body=predict_body, raw=raw)


def generate(
    meta: ArtifactMetadata,
    artifact_dest: str,
    *,
    model: str | None = None,
) -> GeneratedCode:
    """Call Groq and return generated load() and predict() method bodies."""
    _check_api_key()

    if Groq is None:
        raise SystemExit(
            "Error: groq package not installed.\n"
            "Install with: pip install groq"
        )

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    chosen_model = model or os.environ.get("INFERENCE_ENGINE_LLM_MODEL", _DEFAULT_MODEL)

    print(f"\n[Generating load() and predict() via Groq ({chosen_model})...]")

    response = client.chat.completions.create(
        model=chosen_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(meta, artifact_dest)},
        ],
        temperature=0.1,
        max_tokens=512,
    )

    raw = response.choices[0].message.content.strip()
    load_body, predict_body = _parse_methods(raw)

    return GeneratedCode(load_body=load_body, predict_body=predict_body, raw=raw)
