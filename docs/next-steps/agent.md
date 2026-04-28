# Agent: Model Setup CLI

An interactive CLI agent that takes a trained model artifact (`.pkl`, `.joblib`, etc.),
inspects it, asks the user a few questions, and generates a fully working pipeline
definition — ready to serve immediately.

Think: `npm create vite@latest`, but for plugging a model into the inference engine.

---

## Invocation

```bash
inference-engine init ./my_model.pkl
```

Or without a path (agent will ask):

```bash
inference-engine init
```

---

## What the agent does NOT generate

The engine has a fixed contract. Every pipeline is:

```
pre-process → validate → model.predict() → post-process
```

And every definition file has the same structure — `MODEL_NAME`, `MODEL_VERSION`,
`build_pipeline()`. The agent never generates this scaffolding from scratch.
It fills in two things only:

1. `load()` — how to deserialize the artifact
2. `predict()` — how to call the model and return a result

Everything else is a template. The LLM's creative surface is intentionally minimal.

---

## Flow

```
$ inference-engine init ./sentiment.pkl

[Inspector]
✓ Detected: sklearn Pipeline
  └─ TfidfVectorizer → LogisticRegression
  └─ Input: raw text strings
  └─ Output: integer class label (classes: [0, 1])
  └─ Artifact size: 2.3 MB

[Prompts]
? Model name: sentiment
? Version: v1
? Execution target: (cpu / gpu) › cpu
? Routing strategy: (static / canary / ab) › static
? Provide a sample input for validation: "this movie was great"

[Agent — generating load() and predict()]
  Calling LLM...

[Validation]
  Loading pipeline...
  Running with sample input...
✓ Output: 1  (pipeline works)

[Preview]
  models/sentiment/v1/definition.py     [new]
  models/sentiment/v1/sentiment.pkl     [copied]
  app/config/routing.py                 [patched]

? Write these files? (Y/n) › Y

✓ Done.

Test it:
  curl -X POST http://localhost:8000/predict \
    -H "X-API-Key: dev-key" \
    -d '{"model": "sentiment", "version": "v1", "data": "this movie was great"}'
```

---

## Architecture

```
app/cli/
├── __main__.py        entry point — parses args, runs init command
├── init.py            orchestrates the full flow
├── inspector.py       pickle introspection — extracts metadata
├── agent.py           LLM call — generates load() and predict() bodies
├── validator.py       runs the generated pipeline in-process, returns result or error
└── writer.py          writes files and patches routing.py
```

Entry point registered in `pyproject.toml`:
```toml
[project.scripts]
inference-engine = "app.cli.__main__:main"
```

---

## Inspector (`inspector.py`)

Unpickles the artifact and extracts structured metadata to hand to the LLM.

```python
@dataclass
class ArtifactMetadata:
    framework: str          # "sklearn" | "pytorch" | "generic"
    class_name: str         # e.g. "Pipeline", "RandomForestClassifier"
    class_hierarchy: list   # for sklearn Pipelines: list of step class names
    input_hint: str         # e.g. "array-like shape (n, 4)" or "raw text string"
    output_hint: str        # e.g. "integer class label" or "float"
    feature_count: int | None
    class_labels: list | None
    artifact_path: str
```

Detection logic:
- Check `type(obj).__module__` for `sklearn`, `torch`, `xgboost`, etc.
- For sklearn: walk `.steps` on `Pipeline`, read `n_features_in_`, `classes_`
- For unknown types: set `framework = "generic"`, fill what's available

The inspector never fails hard — it fills what it can and leaves the rest as `None`.
The LLM handles gaps.

---

## Agent (`agent.py`)

Receives `ArtifactMetadata` + user answers. Calls the LLM with a tightly scoped prompt.

**System prompt (fixed):**
```
You are generating two Python method bodies for an ML inference engine.
The engine has a fixed structure. You only write load() and predict().

Rules:
- load() must assign the loaded model to self._model
- predict() receives a single input x and returns a single output
- No imports inside methods unless necessary
- No print statements
- Return only the two method bodies, nothing else
```

**User prompt (constructed from metadata):**
```
Artifact: sklearn Pipeline [TfidfVectorizer → LogisticRegression]
Input: raw text string
Output: integer class label (classes: [0, 1])
Artifact path: models/sentiment/v1/sentiment.pkl

Write load() and predict().
```

**LLM output (expected):**
```python
def load(self):
    import joblib
    self._model = joblib.load("models/sentiment/v1/sentiment.pkl")

def predict(self, x):
    return int(self._model.predict([x])[0])
```

The agent injects these bodies into the fixed `definition.py` template.

**LLM backend:** configurable via `INFERENCE_ENGINE_LLM_PROVIDER` env var.
- `openai` (default) — gpt-4o
- `anthropic` — claude-3-5-sonnet
- `ollama` — local model, no API key required

---

## Validation loop (`validator.py`)

After generation, before writing any files:

1. Write the generated `definition.py` to a temp directory
2. Import it and call `build_pipeline()`
3. Run `pipeline.run(sample_input)`
4. If it succeeds → proceed to write
5. If it fails → send the traceback back to the LLM with: *"This failed. Fix it."*
6. Retry up to **3 times**
7. If still failing → show the error to the user and exit cleanly

The validation loop is what makes the agent reliable rather than just plausible.
The fixed pipeline structure means the only things that can go wrong are inside
`load()` and `predict()` — a small, well-defined surface for the LLM to fix.

---

## Writer (`writer.py`)

Only runs after the user confirms the preview.

1. `mkdir -p models/<name>/<version>/`
2. Copy artifact to `models/<name>/<version>/<filename>`
3. Write `models/<name>/<version>/definition.py`
4. Patch `app/config/routing.py` — append the new model's routing entry
5. Print the test curl command

Routing patch is a simple AST rewrite on the `ROUTES` dict — not regex, not string
append. Uses `ast` module to parse and `astor` or manual formatting to write back.

---

## New dependencies

```toml
[project.optional-dependencies]
cli = [
    "questionary>=2.0.0",
    "rich>=13.0.0",
    "openai>=1.0.0",
]
```

Optional — the CLI is an opt-in extra. The core engine has no new runtime dependencies.

Install with: `pip install inference-engine[cli]`

---

## What the agent does NOT do

- Does not write custom preprocessors or postprocessors. If the user needs those,
  the agent tells them which file to edit and what interface to implement.
- Does not handle PyTorch `.pt` files in v1. The inspector detects PyTorch and
  tells the user: *"PyTorch models are not yet supported. Use the manual flow."*
- Does not modify any engine internals. It only writes files under `models/` and
  patches `app/config/routing.py`.

---

## Build order

1. `inspector.py` — pure Python, no LLM, fully testable in isolation
2. `init.py` prompt flow — questionary session, no LLM
3. `agent.py` — LLM call with fixed prompt structure
4. `validator.py` — in-process pipeline execution + retry loop
5. `writer.py` — file write + routing patch
6. Wire into `__main__.py` and register the entry point
