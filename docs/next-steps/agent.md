# Model Setup CLI — Design & Build Plan

An interactive CLI that takes a trained model artifact, inspects it, generates
`load()` and `predict()` via LLM, validates the pipeline, and registers it with
the inference engine — all in one command.

Target user: a developer who already has the engine running and wants to deploy
a new model without writing boilerplate by hand.

---

## Invocation

```bash
inference-engine deploy ./sentiment.pkl
```

With explicit options (CI / scripted):

```bash
inference-engine deploy ./sentiment.pkl \
  --name sentiment \
  --version v2 \
  --device cpu \
  --routing static \
  --sample-input "this movie was great"
```

Fix a broken existing pipeline:

```bash
inference-engine fix models/sentiment/v1/
```

---

## What the CLI does NOT generate

The engine has a fixed pipeline contract:

```
pre-process → validate → model.predict() → post-process
```

Every definition file has the same structure: `MODEL_NAME`, `MODEL_VERSION`,
`build_pipeline()`. The CLI never generates this scaffolding — it fills in two
things only:

1. `load()` — how to deserialize the artifact
2. `predict()` — how to call the model and return a result

Everything else is a fixed template. The LLM's creative surface is intentionally
minimal. This is what makes the output reliable and auditable.

---

## Versioning

Auto-increment by default. If `models/sentiment/` has no versions, create `v1`.
If `v1` exists, create `v2`. The user can override with `--version`.

Name is derived from the filename if `--name` is not provided:
`sentiment.pkl` → `sentiment`.

---

## File placement

All generated files go into the auto-discovery path, not the hardcoded definitions
dict. The registry scans this directory at startup — no manual registration needed.

```
models/
└── sentiment/
    └── v1/
        ├── definition.py     ← generated
        └── sentiment.pkl     ← artifact copied here
```

`app/config/routing.py` is patched to add the new model's routing entry.

---

## Server lifecycle

`deploy` is file-only. It writes files and exits. The user restarts uvicorn and
the registry picks up the new model via auto-discovery.

With `--hot` (optional, requires a running server): hits `POST /admin/reload`
to trigger a live registry refresh without restart. This endpoint does not exist
yet and is out of scope for the initial phases.

---

## Full flow

```
$ inference-engine deploy ./sentiment.pkl

⚠ Warning: loading a pickle file executes arbitrary Python code.
  Only load artifacts from sources you trust.
  Continue? (Y/n) › Y

[Inspector]
✓ Detected: sklearn Pipeline
  └─ TfidfVectorizer → LogisticRegression
  └─ Input: raw text strings
  └─ Output: integer class label (classes: [0, 1])
  └─ Artifact size: 2.3 MB

[Prompts]
? Model name: sentiment
? Version (auto: v1): v1
? Execution target (cpu / gpu): cpu
? Routing strategy (static / canary / ab): static
? Sample input for validation: "this movie was great"

[Generating load() and predict() via LLM...]

[Validation]
  Loading pipeline in temp directory...
  Running with sample input...
✓ Output: 1

[Preview]
  models/sentiment/v1/definition.py     [new]
  models/sentiment/v1/sentiment.pkl     [copied]
  app/config/routing.py                 [patched]

? Write these files? (Y/n) › Y

✓ Done. Restart the server to load the model.

Test it:
  curl -X POST http://localhost:8000/predict \
    -H "X-API-Key: dev-key" \
    -d '{"model": "sentiment", "version": "v1", "data": "this movie was great"}'
```

---

## Architecture

```
app/cli/
├── __main__.py        entry point — parses args, dispatches commands
├── deploy.py          orchestrates the full deploy flow
├── fix.py             orchestrates the fix flow
├── inspector.py       artifact introspection — extracts metadata
├── agent.py           LLM call — generates load() and predict() bodies
├── validator.py       runs the generated pipeline in a temp dir, returns result or error
└── writer.py          writes files and patches routing.py
```

Entry point in `pyproject.toml`:

```toml
[project.scripts]
inference-engine = "app.cli.__main__:main"
```

---

## Component specs

### Inspector (`inspector.py`)

Unpickles the artifact in an isolated subprocess and extracts structured metadata.

```python
@dataclass
class ArtifactMetadata:
    framework: str           # "sklearn" | "pytorch" | "generic"
    class_name: str          # e.g. "Pipeline", "RandomForestClassifier"
    class_hierarchy: list    # for sklearn Pipelines: list of step class names
    input_hint: str          # e.g. "array-like shape (n, 4)" or "raw text string"
    output_hint: str         # e.g. "integer class label" or "float"
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

**Security — pickle sandboxing:** `pickle.load()` executes arbitrary Python code.
The inspector must run in an isolated subprocess with a timeout and no network access.

```python
def inspect_artifact(path: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _INSPECT_SCRIPT.format(path=path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"Inspection failed: {result.stderr}")
    return json.loads(result.stdout)
```

Always show the pickle warning before loading any artifact.

---

### Agent (`agent.py`)

Receives `ArtifactMetadata` + user answers. Calls the LLM with a tightly scoped prompt.

**System prompt (fixed):**
```
You are generating two Python method bodies for an ML inference engine.
You only write load() and predict().

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

LLM backend is configurable via `INFERENCE_ENGINE_LLM_PROVIDER`:
- `openai` (default) — gpt-4o
- `anthropic` — claude-3-5-sonnet
- `ollama` — local model, no API key required

Pre-flight key check before any LLM call:

```python
def _check_provider_key(provider: str) -> None:
    key_map = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
    if provider in key_map and not os.environ.get(key_map[provider]):
        raise SystemExit(
            f"Error: {key_map[provider]} is not set.\n"
            f"Set it with: export {key_map[provider]}=<your-key>"
        )
```

---

### Validation loop (`validator.py`)

After generation, before writing any files:

1. Write the generated `definition.py` to a temp directory
2. Import it and call `build_pipeline()`
3. Run `pipeline.run(sample_input)`
4. If it succeeds → proceed to write
5. If it fails → send the traceback back to the LLM: *"This failed. Fix it."*
6. Retry up to 3 times
7. If still failing → show the error and exit cleanly without writing anything

The fixed pipeline structure means the only things that can go wrong are inside
`load()` and `predict()` — a small, well-defined surface for the LLM to fix.

---

### Writer (`writer.py`)

Only runs after the user confirms the preview.

1. `mkdir -p models/<name>/<version>/`
2. Copy artifact to `models/<name>/<version>/<filename>`
3. Write `models/<name>/<version>/definition.py`
4. Patch `app/config/routing.py` — append the new model's routing entry using
   AST rewrite (not regex or string append)
5. Print the test curl command

---

### Fix command (`fix.py`)

```bash
inference-engine fix models/sentiment/v1/
```

1. Read the existing `definition.py`
2. Run the validation loop against it
3. If it fails, send the error + current code to the LLM for a fix
4. Show a diff preview
5. Write only after user confirms

---

## Non-interactive / CI support

All prompts must be skippable via flags. When all required flags are provided,
no prompts are shown.

Detect non-TTY with `sys.stdin.isatty()` and fail with a clear error if required
flags are missing rather than hanging on a prompt.

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

The CLI is an opt-in extra. The core engine gains no new runtime dependencies.

Install with: `pip install -e ".[cli]"` or `uv sync --extra cli`

---

## Limitations (v1)

- PyTorch `.pt` files are not supported. The inspector detects PyTorch and tells
  the user to use the manual flow.
- Custom preprocessors and postprocessors are not generated. The CLI tells the
  user which file to edit and what interface to implement.
- `--hot` reload is not implemented. Restart the server after deploy.
- No Playground UI. Use the printed curl command to test.

---

---

# Build Phases

The full feature is built incrementally. Each phase is independently testable
and leaves the engine in a working state. No phase cuts scope — later phases
complete what earlier phases defer.

---

## Phase 1 — CLI skeleton + inspector

**Goal:** `inference-engine deploy ./model.pkl` runs, inspects the artifact, and
prints metadata. No LLM, no file writes.

**Deliverables:**
- `app/cli/__main__.py` — entry point, `deploy` subcommand wired
- `app/cli/inspector.py` — subprocess-isolated inspection, returns `ArtifactMetadata`
- `pyproject.toml` — entry point registered, `cli` optional dependency group added
- Pickle safety warning shown before any load
- sklearn detection working; PyTorch and generic fallback working
- Non-TTY detection in place (fail fast if piped and no flags)

**Not in this phase:** prompts, LLM, validation, file writes.

**Test:** `inference-engine deploy tests/fixtures/echo.pkl` prints detected
framework, class name, input/output hints, and artifact size.

---

## Phase 2 — Interactive prompt flow + versioning

**Goal:** After inspection, the CLI asks the user for name, version, device,
routing strategy, and sample input. Auto-increments version. No LLM yet.

**Deliverables:**
- `app/cli/deploy.py` — orchestrates inspect → prompt → preview
- `questionary` prompt session with all required fields
- Auto-version logic: scan `models/<name>/` for existing versions, suggest next
- Preview table (files that would be written) shown before any confirmation
- All prompts skippable via CLI flags (non-interactive mode complete)

**Not in this phase:** LLM call, actual file writes.

**Test:** Run the full prompt flow against a fixture artifact. Confirm preview
output is correct. Confirm `--name x --version v1 --device cpu --routing static
--sample-input foo` skips all prompts.

---

## Phase 3 — LLM code generation

**Goal:** After prompts, call the LLM and generate `load()` and `predict()`.
Print the generated code. No validation or file writes yet.

**Deliverables:**
- `app/cli/agent.py` — fixed system prompt, user prompt constructed from metadata,
  LLM call, response parsed into two method bodies
- Provider selection via `INFERENCE_ENGINE_LLM_PROVIDER`
- Pre-flight API key check for openai and anthropic
- `ollama` provider support (no key required)
- Generated code printed to terminal for inspection

**Not in this phase:** validation loop, file writes.

**Test:** Run against a sklearn fixture with `INFERENCE_ENGINE_LLM_PROVIDER=openai`.
Confirm generated `load()` uses `joblib.load` and `predict()` returns the right type.
Run with `ollama` to confirm no-key path works.

---

## Phase 4 — Validation loop

**Goal:** Validate the generated code before writing anything. Retry on failure.

**Deliverables:**
- `app/cli/validator.py` — writes definition to temp dir, imports it, runs
  `pipeline.run(sample_input)`, returns success or error + traceback
- Retry loop in `deploy.py`: up to 3 attempts, each failure sends traceback back
  to the LLM
- On 3 failures: print the last error and exit cleanly without writing any files
- On success: show the preview and ask for confirmation

**Test:** Intentionally break the LLM prompt to produce bad code. Confirm the
retry loop fires and eventually either fixes it or exits cleanly. Confirm no
files are written on failure.

---

## Phase 5 — File writer + routing patch

**Goal:** After user confirmation, write the files and patch routing config.

**Deliverables:**
- `app/cli/writer.py` — mkdir, copy artifact, write `definition.py`, patch
  `app/config/routing.py` via AST rewrite
- Routing patch handles all three strategies (static, canary, ab)
- Print the test curl command after successful write
- Idempotent: re-running with the same name/version overwrites with a warning,
  does not duplicate routing entries

**Test:** Full end-to-end deploy of a sklearn fixture. Confirm `models/` structure,
confirm `routing.py` is valid Python after patch, confirm the engine serves the
model after server restart.

---

## Phase 6 — Fix command

**Goal:** `inference-engine fix models/sentiment/v1/` reads an existing broken
pipeline, runs the validation loop, and proposes a fix.

**Deliverables:**
- `app/cli/fix.py` — reads existing `definition.py`, runs validator, sends
  error + code to LLM, shows diff, writes after confirmation
- `fix` subcommand registered in `__main__.py`
- Same retry loop as deploy (3 attempts)

**Test:** Manually break a generated `definition.py`. Run `fix`. Confirm the
diff is shown and the fixed file passes validation before being written.

---

## Phase 7 — Polish + hardening

**Goal:** Production-ready CLI. No new features — only reliability and UX.

**Deliverables:**
- Rich terminal output (progress spinners, coloured status, formatted tables)
- Comprehensive error messages for every known failure mode (bad artifact path,
  missing API key, unsupported framework, routing patch conflict, etc.)
- `--dry-run` flag: runs the full flow including validation but writes nothing
- Full test suite for all CLI components with fixture artifacts
- README section updated with CLI usage, env vars, and supported frameworks
- `INFERENCE_ENGINE_LLM_PROVIDER` and API key vars documented in `.env.example`
