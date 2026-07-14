"""LLM interpretation stage — enriches ArtifactMetadata when inspection is incomplete.

This module sits between inspection/spec_builder and codegen in the deploy pipeline.
It fires when DeploymentSpecCandidate.deployment_readiness != "ready", calling an LLM
to fill in ambiguous fields (framework, load_format, input/output hints).

Pipeline position:
    inspect_artifact() → build_deployment_spec() → [interpret()] → generate()

Design:
    - Graceful degradation: if the LLM call fails, returns None and the pipeline
      proceeds with unpatched metadata (codegen will try its best).
    - Interactive mode: presents at most 2 multiple-choice questions to the user
      when the LLM flags remaining ambiguity.
    - Non-interactive mode: auto-accepts the LLM's suggested answer.
"""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from app.cli.core.inspector import ArtifactMetadata, FieldValue
from app.cli.core.spec_builder import DeploymentSpecCandidate

try:
    from groq import Groq
except ImportError:
    Groq = None  # type: ignore[assignment,misc]

console = Console()

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_MAX_QUESTIONS = 2


# ---------------------------------------------------------------------------
# InterpretationResult — structured LLM response
# ---------------------------------------------------------------------------

@dataclass
class InterpretationResult:
    """Structured result from the LLM interpretation stage.

    Attributes:
        framework: Interpreted ML framework (e.g. "xgboost", "pytorch") or None.
        load_format: How to load the artifact (e.g. "joblib", "state_dict") or None.
        input_hint: Description of model input format.
        output_hint: Description of model output format.
        confidence: LLM's self-assessed confidence ("high", "medium", "low").
        suggested_sample_input: A sample input string the LLM suggests for validation.
        question: A clarifying question if ambiguity remains, else None.
        question_field: Which field the question is about (e.g. "load_format").
        options: Multiple-choice options for the question.
        suggested_answer: The LLM's recommended answer from options.
    """

    framework: str | None
    load_format: str | None
    input_hint: str | None
    output_hint: str | None
    confidence: str
    suggested_sample_input: str | None
    question: str | None
    question_field: str | None
    options: list[str] | None
    suggested_answer: str | None


# ---------------------------------------------------------------------------
# System prompt for the interpretation LLM call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an ML model artifact analyst. Given raw inspection facts about a model artifact,
you determine the correct framework, loading strategy, and input/output format.

You receive a partially-filled deployment spec to enrich — do NOT build from scratch.

Return ONLY a JSON object with these fields:
{
  "framework": "<framework name or null if truly unknown>",
  "load_format": "<how to load: joblib, pickle, state_dict, full_model, onnxruntime, etc.>",
  "input_hint": "<description of expected input format>",
  "output_hint": "<description of expected output format>",
  "confidence": "<high|medium|low>",
  "suggested_sample_input": "<a valid sample input as a string, or null>",
  "question": "<one short specific question if a critical unknown remains, else null>",
  "question_field": "<which field the question resolves: framework, load_format, input_hint, or null>",
  "options": ["<option1>", "<option2>", ...] or null,
  "suggested_answer": "<your best guess from options, or null>"
}

Rules:
- Be specific: "numpy array, shape (n_samples, 4)" not just "array"
- Only ask a question when you genuinely cannot determine the answer from the facts
- Return valid JSON only — no markdown, no explanation text
- confidence is YOUR confidence in the interpretation, not the artifact's quality
"""


# ---------------------------------------------------------------------------
# _build_interpretation_prompt — constructs the user message for the LLM
# ---------------------------------------------------------------------------

def _build_interpretation_prompt(
    meta: ArtifactMetadata,
    spec: DeploymentSpecCandidate,
    *,
    sample_input: str | None,
) -> str:
    """Build the user prompt for the interpretation LLM call.

    Includes raw_facts, spec readiness, inspection errors, and sample input.
    """
    sections: list[str] = []

    # Raw facts from inspection
    sections.append("## Raw Inspection Facts")
    sections.append(json.dumps(meta.raw_facts, indent=2, default=str))

    # Deployment spec status
    sections.append("\n## Deployment Spec (current state)")
    sections.append(f"- Framework: {spec.framework}")
    sections.append(f"- Artifact type: {spec.artifact_type}")
    sections.append(f"- Loader strategy: {spec.loader_strategy}")
    sections.append(f"- Required packages: {spec.required_packages}")
    sections.append(f"- Capabilities: {spec.capabilities}")
    sections.append(f"- Deployment readiness: {spec.deployment_readiness}")

    # Inspection errors
    if meta.inspection_errors:
        sections.append("\n## Inspection Errors")
        for err in meta.inspection_errors:
            if isinstance(err, dict):
                sections.append(f"- [{err.get('layer', '?')}] {err.get('error', '?')}")
            else:
                sections.append(f"- {err}")

    # Framework hint (user-provided via --framework flag)
    hint = meta.raw_facts.get("framework_hint")
    if hint:
        sections.append(f"\n## User-Provided Framework Hint: {hint}")

    # Sample input
    if sample_input is not None:
        sections.append(f"\n## Sample Input Provided: {sample_input}")

    sections.append("\n## Task")
    sections.append(
        "Analyze the above facts and fill in the missing/uncertain fields. "
        "Return the JSON response."
    )

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# _parse_interpretation_response — extract InterpretationResult from LLM output
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("framework", "load_format", "input_hint", "output_hint", "confidence")


def _parse_interpretation_response(raw: str) -> InterpretationResult:
    """Parse the LLM's JSON response into an InterpretationResult.

    Handles markdown fences, missing optional fields. Raises ValueError on
    invalid JSON or missing required fields.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse LLM interpretation response as JSON: {e}")

    # Validate required fields
    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(
            f"Could not parse LLM interpretation response: missing required fields: {missing}"
        )

    return InterpretationResult(
        framework=data.get("framework"),
        load_format=data.get("load_format"),
        input_hint=data.get("input_hint"),
        output_hint=data.get("output_hint"),
        confidence=data.get("confidence", "low"),
        suggested_sample_input=data.get("suggested_sample_input"),
        question=data.get("question"),
        question_field=data.get("question_field"),
        options=data.get("options"),
        suggested_answer=data.get("suggested_answer"),
    )


# ---------------------------------------------------------------------------
# apply_interpretation — patch ArtifactMetadata with LLM results
# ---------------------------------------------------------------------------

def _should_llm_overwrite(existing: FieldValue | None, new_value: FieldValue) -> bool:
    """Determine whether the LLM value should replace the existing field.

    The LLM wins when:
    - The existing field is None
    - The existing value is useless ("unknown", None, "generic", "")
    - The existing source has lower priority than "llm" (i.e. "default")

    The LLM loses when:
    - The existing source is "user" (highest priority — explicit flag)
    - The existing value is meaningful AND from a higher-priority source (extractor)
    """
    if existing is None:
        return True

    # User-provided values are sacrosanct
    if existing.source == "user":
        return False

    # If existing value is useless/unknown, LLM always wins
    _USELESS = (None, "", "unknown", "generic")
    if existing.value in _USELESS:
        return True

    # Otherwise respect source priority: only overwrite if LLM priority >= existing
    return FieldValue.source_priority("llm") >= FieldValue.source_priority(existing.source)


def apply_interpretation(
    meta: ArtifactMetadata,
    result: InterpretationResult,
) -> ArtifactMetadata:
    """Patch ArtifactMetadata fields with interpretation results.

    Uses _should_llm_overwrite() to decide per-field: the LLM overwrites useless
    values (unknown/None) from any source, but defers to user-provided values.

    Returns a new ArtifactMetadata instance — does not mutate the original.
    """
    patched = copy.copy(meta)

    confidence = result.confidence

    # Patch framework
    if result.framework is not None:
        new_fw = FieldValue(value=result.framework, source="llm", confidence=confidence)
        if _should_llm_overwrite(meta.framework, new_fw):
            patched.framework = new_fw

    # Patch load_format
    if result.load_format is not None:
        new_lf = FieldValue(value=result.load_format, source="llm", confidence=confidence)
        if _should_llm_overwrite(meta.load_format, new_lf):
            patched.load_format = new_lf

    # Patch input_hint
    if result.input_hint is not None:
        new_ih = FieldValue(value=result.input_hint, source="llm", confidence=confidence)
        if _should_llm_overwrite(meta.input_hint, new_ih):
            patched.input_hint = new_ih

    # Patch output_hint
    if result.output_hint is not None:
        new_oh = FieldValue(value=result.output_hint, source="llm", confidence=confidence)
        if _should_llm_overwrite(meta.output_hint, new_oh):
            patched.output_hint = new_oh

    # Update interpretation confidence
    patched.interpretation_confidence = confidence

    return patched


# ---------------------------------------------------------------------------
# _ask_question — interactive multiple-choice prompt
# ---------------------------------------------------------------------------

def _ask_question(result: InterpretationResult) -> str:
    """Present a multiple-choice question to the user and return the chosen answer.

    Displays options with (recommended) tag on the suggested_answer.
    Returns the selected option string.
    """
    console.print(f"\n[bold]? {result.question}[/bold] [dim]({result.question_field})[/dim]")

    options = result.options or []
    suggested = result.suggested_answer

    for i, opt in enumerate(options, 1):
        tag = " [green](recommended)[/green]" if opt == suggested else ""
        console.print(f"  [{i}] {opt}{tag}")

    console.print("  [dim](Press Enter for recommended)[/dim]")

    try:
        choice = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    if not choice:
        # Empty → use recommended
        return suggested or (options[0] if options else "")

    try:
        idx = int(choice)
        if 1 <= idx <= len(options):
            return options[idx - 1]
    except (ValueError, IndexError):
        pass

    # Invalid input → fall back to recommended
    return suggested or (options[0] if options else "")


# ---------------------------------------------------------------------------
# interpret() — main entry point
# ---------------------------------------------------------------------------

def interpret(
    meta: ArtifactMetadata,
    spec: DeploymentSpecCandidate,
    *,
    sample_input: str | None,
    interactive: bool = False,
) -> InterpretationResult | None:
    """Run the LLM interpretation stage.

    Skips entirely if spec.deployment_readiness == "ready" (no ambiguity).
    Returns None on failure (missing API key, network error, bad response)
    with a console warning — the pipeline proceeds with unpatched metadata.

    Args:
        meta: ArtifactMetadata from inspection.
        spec: DeploymentSpecCandidate from spec_builder.
        sample_input: Optional sample input string.
        interactive: Whether to prompt the user for clarifying questions.

    Returns:
        InterpretationResult on success, None if skipped or failed.
    """
    # Skip if artifact is already ready — no LLM call needed
    if spec.deployment_readiness == "ready":
        return None

    # Check API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        console.print(
            "[yellow]Warning:[/yellow] GROQ_API_KEY not set — skipping LLM interpretation stage."
        )
        return None

    if Groq is None:
        console.print(
            "[yellow]Warning:[/yellow] groq package not installed — skipping interpretation."
        )
        return None

    # Build prompt
    user_prompt = _build_interpretation_prompt(meta, spec, sample_input=sample_input)

    # Call LLM
    chosen_model = os.environ.get("INFERENCE_ENGINE_LLM_MODEL", _DEFAULT_MODEL)

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        raw_content = response.choices[0].message.content.strip()
    except Exception as e:
        console.print(
            f"[yellow]Warning:[/yellow] LLM interpretation failed: {e}. "
            "Proceeding with unpatched metadata."
        )
        return None

    # Parse response
    try:
        result = _parse_interpretation_response(raw_content)
    except ValueError as e:
        console.print(
            f"[yellow]Warning:[/yellow] Could not parse LLM response: {e}. "
            "Proceeding with unpatched metadata."
        )
        return None

    # Handle clarifying questions
    if result.question and result.options and interactive:
        answer = _ask_question(result)
        # Patch the result with the user's choice
        if result.question_field == "framework":
            result = InterpretationResult(
                framework=answer,
                load_format=result.load_format,
                input_hint=result.input_hint,
                output_hint=result.output_hint,
                confidence=result.confidence,
                suggested_sample_input=result.suggested_sample_input,
                question=None,
                question_field=None,
                options=None,
                suggested_answer=None,
            )
        elif result.question_field == "load_format":
            result = InterpretationResult(
                framework=result.framework,
                load_format=answer,
                input_hint=result.input_hint,
                output_hint=result.output_hint,
                confidence=result.confidence,
                suggested_sample_input=result.suggested_sample_input,
                question=None,
                question_field=None,
                options=None,
                suggested_answer=None,
            )
        elif result.question_field == "input_hint":
            result = InterpretationResult(
                framework=result.framework,
                load_format=result.load_format,
                input_hint=answer,
                output_hint=result.output_hint,
                confidence=result.confidence,
                suggested_sample_input=result.suggested_sample_input,
                question=None,
                question_field=None,
                options=None,
                suggested_answer=None,
            )

    return result
