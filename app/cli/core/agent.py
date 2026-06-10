"""LLM code generation for load() and predict() via Groq — Phase 3."""
from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass

from app.cli.core.inspector import ArtifactMetadata

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
- predict() must return a plain Python type (int, float, str, list) — never a numpy scalar or tensor
- Always import any module you use at the top of the method (e.g. import joblib, import pickle)
- No print statements
- Return ONLY the two method bodies as plain Python, no class wrapper, no markdown fences
- Use exactly these signatures:
    def load(self) -> None:
    def predict(self, x):
"""


def _framework_hints(meta: ArtifactMetadata) -> list[str]:
    """Return per-framework hint lines to append to the user prompt."""
    fw = meta.framework
    extra = meta.extra if hasattr(meta, "extra") and meta.extra else {}
    hints: list[str] = []

    if fw == "pytorch":
        hints += [
            "",
            "Framework hints (PyTorch):",
            "- load(): use torch.load(path, map_location='cpu') and call self._model.eval()",
            "- predict(): convert input to torch.Tensor, run through self._model, return .tolist() or .item()",
            "- Wrap inference in torch.no_grad()",
        ]
        if extra.get("layer_count"):
            hints.append(f"- Layer count: {extra['layer_count']}")
    elif fw == "transformers":
        hints += [
            "",
            "Framework hints (Hugging Face Transformers):",
            "- load(): use AutoModel.from_pretrained(path) and AutoTokenizer.from_pretrained(path)",
            "- predict(): tokenize input string, run model(**inputs), return logits or embeddings as list",
            "- Use torch.no_grad() during inference",
        ]
        if extra.get("model_type"):
            hints.append(f"- Model type: {extra['model_type']}")
        if extra.get("num_labels"):
            hints.append(f"- Num labels: {extra['num_labels']}")
        if extra.get("tokenizer_class"):
            hints.append(f"- Tokenizer class: {extra['tokenizer_class']}")
    elif fw == "xgboost":
        hints += [
            "",
            "Framework hints (XGBoost):",
            "- load(): use joblib.load(path) for XGBModel, or xgb.Booster() + booster.load_model(path)",
            "- predict(): convert input to numpy array, call self._model.predict(np.array([x]))[0]",
            "- Return a plain Python int or float, not a numpy scalar",
        ]
        if extra.get("n_estimators"):
            hints.append(f"- n_estimators: {extra['n_estimators']}")
        if extra.get("objective"):
            hints.append(f"- Objective: {extra['objective']}")
    elif fw == "lightgbm":
        hints += [
            "",
            "Framework hints (LightGBM):",
            "- load(): use joblib.load(path) for LGBMModel, or lgb.Booster(model_file=path)",
            "- predict(): call self._model.predict(np.array([x]))[0]",
            "- Return a plain Python int or float",
        ]
        if extra.get("n_estimators"):
            hints.append(f"- n_estimators: {extra['n_estimators']}")
        if extra.get("objective"):
            hints.append(f"- Objective: {extra['objective']}")
    elif fw == "catboost":
        hints += [
            "",
            "Framework hints (CatBoost):",
            "- load(): use joblib.load(path) or CatBoost().load_model(path)",
            "- predict(): call self._model.predict([x])[0]",
            "- Return a plain Python int or float",
        ]
        if extra.get("loss_function"):
            hints.append(f"- Loss function: {extra['loss_function']}")
    elif fw == "onnx":
        hints += [
            "",
            "Framework hints (ONNX Runtime):",
            "- load(): use onnxruntime.InferenceSession(path) and store as self._session",
            "- predict(): get input name via self._session.get_inputs()[0].name",
            "  run: self._session.run(None, {input_name: np.array([x], dtype=np.float32)})[0][0]",
            "- Return a plain Python type",
        ]
        if extra.get("onnx_inputs"):
            hints.append(f"- ONNX inputs: {extra['onnx_inputs']}")
        if extra.get("onnx_outputs"):
            hints.append(f"- ONNX outputs: {extra['onnx_outputs']}")
    elif fw == "sentence_transformers":
        hints += [
            "",
            "Framework hints (sentence-transformers):",
            "- load(): use SentenceTransformer(path) from sentence_transformers",
            "- predict(): call self._model.encode(x).tolist()",
            "- Input x is a string; output is a list of floats (embedding vector)",
        ]
        if extra.get("embedding_dim"):
            hints.append(f"- Embedding dim: {extra['embedding_dim']}")

    return hints


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
    lines.extend(_framework_hints(meta))
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
    raw = re.sub(r"```(?:python)?", "", raw).replace("```", "").strip()
    # Unwrap class body: de-indent methods so top-level def splitting works
    raw = re.sub(r"^class\s+\w.*?\n", "", raw, count=1, flags=re.MULTILINE)
    raw = textwrap.dedent(raw).strip()

    methods: dict[str, str] = {}
    for block in re.split(r"(?=^def )", raw, flags=re.MULTILINE):
        block = block.strip()
        if block.startswith("def load(self)"):
            methods["load"] = block
        elif block.startswith("def predict(self,"):
            methods["predict"] = block

    if "load" not in methods or "predict" not in methods:
        raise ValueError(
            f"Could not parse load() and predict() from LLM output:\n{raw}"
        )

    return methods["load"], methods["predict"]


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
