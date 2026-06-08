"""Phase 3 — agent.py tests: LLM code generation via Groq."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Load .env so GROQ_API_KEY is available for the live test skip check
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from app.cli.core.inspector import ArtifactMetadata

FIXTURE = Path(__file__).parent / "fixtures" / "sentiment.pkl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(**kwargs) -> ArtifactMetadata:
    defaults = dict(
        framework="sklearn",
        class_name="Pipeline",
        class_hierarchy=["TfidfVectorizer", "LogisticRegression"],
        input_hint="raw text string",
        output_hint="integer class label (classes: [0, 1])",
        feature_count=None,
        class_labels=[0, 1],
        artifact_path="models/sentiment/v1/sentiment.pkl",
        artifact_size_mb=1.5,
    )
    defaults.update(kwargs)
    return ArtifactMetadata(**defaults)


def _mock_groq_response(content: str):
    """Build a minimal mock that looks like a Groq chat completion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# _check_api_key
# ---------------------------------------------------------------------------

def test_check_api_key_missing(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from app.cli.core.agent import _check_api_key
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        _check_api_key()


def test_check_api_key_present(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    from app.cli.core.agent import _check_api_key
    _check_api_key()  # should not raise


# ---------------------------------------------------------------------------
# _build_user_prompt
# ---------------------------------------------------------------------------

def test_build_user_prompt_contains_key_fields():
    from app.cli.core.agent import _build_user_prompt
    meta = _make_meta()
    prompt = _build_user_prompt(meta, "models/sentiment/v1/sentiment.pkl")
    assert "sklearn" in prompt
    assert "TfidfVectorizer" in prompt
    assert "raw text string" in prompt
    assert "models/sentiment/v1/sentiment.pkl" in prompt
    assert "[0, 1]" in prompt


def test_build_user_prompt_no_hierarchy():
    from app.cli.core.agent import _build_user_prompt
    meta = _make_meta(class_hierarchy=[], class_labels=None, feature_count=4)
    prompt = _build_user_prompt(meta, "models/iris/v1/iris.pkl")
    assert "Feature count: 4" in prompt
    assert "Pipeline steps" not in prompt


# ---------------------------------------------------------------------------
# _parse_methods
# ---------------------------------------------------------------------------

def test_parse_methods_clean():
    from app.cli.core.agent import _parse_methods
    raw = (
        "def load(self) -> None:\n"
        "    import joblib\n"
        "    self._model = joblib.load(self._path)\n"
        "\n"
        "def predict(self, x):\n"
        "    return int(self._model.predict([x])[0])\n"
    )
    load, predict = _parse_methods(raw)
    assert load.startswith("def load(self)")
    assert "self._model" in load
    assert predict.startswith("def predict(self,")
    assert "return" in predict


def test_parse_methods_strips_markdown_fences():
    from app.cli.core.agent import _parse_methods
    raw = (
        "```python\n"
        "def load(self) -> None:\n"
        "    self._model = joblib.load('x')\n"
        "\n"
        "def predict(self, x):\n"
        "    return self._model.predict([x])[0]\n"
        "```"
    )
    load, predict = _parse_methods(raw)
    assert "def load" in load
    assert "def predict" in predict


def test_parse_methods_missing_predict_raises():
    from app.cli.core.agent import _parse_methods
    raw = "def load(self) -> None:\n    self._model = joblib.load('x')\n"
    with pytest.raises(ValueError, match="Could not parse"):
        _parse_methods(raw)


def test_parse_methods_missing_load_raises():
    from app.cli.core.agent import _parse_methods
    raw = "def predict(self, x):\n    return self._model.predict([x])[0]\n"
    with pytest.raises(ValueError, match="Could not parse"):
        _parse_methods(raw)


def test_parse_methods_class_body_wrapped():
    """LLM wraps both methods in a class body — each method must be isolated."""
    from app.cli.core.agent import _parse_methods
    raw = (
        "class _GeneratedModel:\n"
        "    def load(self) -> None:\n"
        "        import joblib\n"
        "        self._model = joblib.load(self._path)\n"
        "\n"
        "    def predict(self, x):\n"
        "        return int(self._model.predict([x])[0])\n"
    )
    load, predict = _parse_methods(raw)
    assert load.startswith("def load(self)")
    assert "self._model" in load
    assert predict.startswith("def predict(self,")
    assert "def predict" not in load
    assert "def load" not in predict


# ---------------------------------------------------------------------------
# generate() — mocked Groq client
# ---------------------------------------------------------------------------

_GOOD_RESPONSE = (
    "def load(self) -> None:\n"
    "    import joblib\n"
    "    self._model = joblib.load(r'models/sentiment/v1/sentiment.pkl')\n"
    "\n"
    "def predict(self, x):\n"
    "    return int(self._model.predict([x])[0])\n"
)


def test_generate_returns_generated_code(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    meta = _make_meta()

    with patch("app.cli.core.agent.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

        from app.cli.core.agent import generate
        result = generate(meta, "models/sentiment/v1/sentiment.pkl")

    assert "def load" in result.load_body
    assert "self._model" in result.load_body
    assert "def predict" in result.predict_body
    assert result.raw == _GOOD_RESPONSE.strip()


def test_generate_uses_env_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("INFERENCE_ENGINE_LLM_MODEL", "mixtral-8x7b-32768")
    meta = _make_meta()

    with patch("app.cli.core.agent.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

        from app.cli.core.agent import generate
        generate(meta, "models/sentiment/v1/sentiment.pkl")

        call_kwargs = instance.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "mixtral-8x7b-32768"


def test_generate_uses_explicit_model_arg(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("INFERENCE_ENGINE_LLM_MODEL", raising=False)
    meta = _make_meta()

    with patch("app.cli.core.agent.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.return_value = _mock_groq_response(_GOOD_RESPONSE)

        from app.cli.core.agent import generate
        generate(meta, "models/sentiment/v1/sentiment.pkl", model="gemma2-9b-it")

        call_kwargs = instance.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gemma2-9b-it"


def test_generate_no_api_key_exits(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    meta = _make_meta()

    from app.cli.core.agent import generate
    with pytest.raises(SystemExit, match="GROQ_API_KEY"):
        generate(meta, "models/sentiment/v1/sentiment.pkl")


def test_generate_bad_llm_output_raises(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    meta = _make_meta()

    with patch("app.cli.core.agent.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.return_value = _mock_groq_response(
            "Sorry, I cannot help with that."
        )

        from app.cli.core.agent import generate
        with pytest.raises(ValueError, match="Could not parse"):
            generate(meta, "models/sentiment/v1/sentiment.pkl")


# ---------------------------------------------------------------------------
# Live integration test (skipped unless GROQ_API_KEY is set)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live Groq call",
)
def test_generate_live_sklearn():
    from app.cli.core.inspector import inspect_artifact
    from app.cli.core.agent import generate

    meta = inspect_artifact(str(FIXTURE))
    result = generate(meta, "models/sentiment/v1/sentiment.pkl")

    assert "self._model" in result.load_body
    assert "def predict" in result.predict_body
    print("\n[Live generated code]\n", result.raw)
