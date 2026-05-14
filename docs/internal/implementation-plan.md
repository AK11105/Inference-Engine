# Implementation Plan — Platform Extensions
*Created: 2026-05-08*
*Last updated: 2026-05-14*
*Based on: `docs/next-steps/proposal.md`*

---

## Guiding Principles

1. **Fixes before features.** Bugs and fragilities in the CLI must be resolved before Phase 9 work begins. They are small in scope and prevent technical debt from compounding.
2. **Each phase is independently shippable.** No phase depends on the next being complete.
3. **LLM usage stays bounded.** Every LLM-generated output goes through the existing validate → repair loop. No new "magic" paths.
4. **No new mandatory dependencies.** New framework support and export targets are opt-in via extras or lazy imports.
5. **Inspector is load-bearing.** All downstream phases — cache keys, metadata API, export adapters, explain mode — depend on the inspector producing reliable output. Phase 8 revision must land before Phase 9 begins.

---

## Pre-Phase: Fixes ✅ Complete

All items from `fixes.md` have been resolved:

1. **Fix 1** — `PostgresJobStore` rewritten with `asyncpg`. `JobStore`, `JobService`, `PredictionService`, `AsyncInferenceService`, all route handlers, and the arq worker are fully async.
2. **Fix 2** — Startup warning logged when `REDIS_URL` is absent. `X-RateLimit-Mode: local|distributed` header added to every response.
3. **Fix 3** — Startup reap in lifespan marks stuck `RUNNING` jobs as `FAILED` before the server accepts requests. Fallback async path uses `asyncio.create_task`.
4. **Fix 4** — README and `docs/guides/adding-a-model.md` updated with the dual-directory layout (`models/` vs `model_artifacts/`).
5. **Fix 5** — `psycopg2` removed from core dependencies. `asyncpg` is the sole Postgres driver.

---

## Phase 8 — Inspector Overhaul + CLI Fixes ⚠️ Revision Required

*Previously marked complete. A detailed audit has identified that the inspector and several CLI components require significant rework before Phase 9 begins. Building Phase 9 on the current inspector will propagate bad metadata into `deployment.json`, the generation cache, and the metadata API.*

*Full details: `docs/inspector-fix.md` and `docs/internal/cli-fixes.md`.*

*Estimated effort: 3–4 weeks*

### 8.1 — Inspector overhaul

The current inspector is a monolithic subprocess script that fails completely on any exception, uses `pickle.load` for all artifact types, and interprets metadata with hardcoded rules. It is replaced with a two-stage design.

**Stage 1 — Layered rule-based extraction (subprocess sandbox)**

The subprocess always exits 0 and always prints valid JSON. Each extraction layer catches its own failures independently and appends to an `errors` list. Partial data is always returned — never a hard failure.

Four layers run in sequence, each building on the last:

- **Layer 0 — Filesystem facts:** extension, size, path. Always succeeds.
- **Layer 1 — Format identification:** extension + magic bytes. Sets `format` and `format_confidence`.
- **Layer 2 — Safe structural read:** format-specific extractor reads structure without executing model code.
- **Layer 3 — Deep attribute scan:** best-effort sklearn/xgb/lgb/catboost attribute extraction. Only runs when Layer 2 succeeded for a pickle-loaded object.

Each artifact format has its own extractor with the correct safe-read strategy:

| Format | Extractor | Safe read strategy |
|---|---|---|
| `.pkl` / `.joblib` | `PickleExtractor` | `joblib.load` first, fallback `pickle.load` → `type`, `__dict__.keys()`, sklearn attributes |
| `.pt` / `.pth` | `TorchExtractor` | `torch.load(..., weights_only=True)` → if dict: state_dict keys (first 30); if Module: layer names, param count |
| `.onnx` | `OnnxExtractor` | `onnx.load` → opset, op_types set (architecture signal), inputs/outputs with `dim_param` for dynamic axes (not `dim_value`) |
| `.safetensors` | `SafetensorsExtractor` | header-only read → tensor keys (first 30), shapes, metadata dict |
| directory | `DirectoryExtractor` | JSON reads only → `config.json` (model_type, architectures, hidden_size, num_labels), `tokenizer_config.json`, presence of `saved_model.pb`, `adapter_config.json` |
| unknown | `GenericExtractor` | tries joblib then pickle, captures what it can, records failure in errors |

`ArtifactMetadata` gains three new fields:
- `raw_facts: dict` — full uninterpreted extraction output, passed to LLM interpretation
- `confidence: str` — `"high"` / `"medium"` / `"low"`, derived from ratio of known fields and presence of errors
- `inspection_errors: list[dict]` — `[{layer, error}]` for `--verbose` display and LLM context

All existing fields that can be unknown are typed as `T | None`. `None` means unknown, not missing.

**Stage 2 — LLM interpretation**

Fires when `confidence < high` or `framework is None`. This is a dedicated LLM call before codegen — not a separate clarify step, but a combined interpret + clarify call.

Input to the call: `raw_facts + inspection_errors + sample_input + --framework hint`

The system prompt instructs the LLM to return a JSON object with:
- `framework`, `load_format`, `input_hint`, `output_hint`, `confidence`
- `question` — one short specific question if a critical unknown remains, else `null`
- `question_field` — which field the question resolves

The clarifying question flow (max 2 questions) asks the user interactively and patches `raw_facts` before re-running interpretation. Skipped entirely in `--yes` / non-interactive mode.

High-confidence artifacts (clean sklearn `.pkl` with all attributes present) skip Stage 2 entirely — no extra API call.

### 8.2 — CLI bug fixes

Six bugs documented in `docs/internal/cli-fixes.md`. All must be resolved in this phase.

**Priority 1 — `sample_input` never parsed (`prompts.py`, `deploy.py`, `fix.py`)**

`sample_input` is passed as a raw string to `pipeline.run()`. Numeric models always fail validation because they receive a string instead of an array. The LLM retries then burn on correct code. Fix: `json.loads` with string fallback before every call to `validate_pipeline`. The raw string is preserved in `DeployAnswers` for the curl example in the writer.

```python
def _parse_sample_input(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw
```

**Priority 2 — `fix` command broken in CI (`fix.py`, `__main__.py`)**

`run_fix` always reads `sample_input` from `input()` and exits if not interactive. No `--sample-input` flag exists on the `fix` subcommand. Fix: add `--sample-input` to `fix` in `__main__.py`; prefer flag value, fall back to `input()` only when interactive and flag not provided.

**Priority 3 — `_splice_methods` corrupts files (`fix.py`)**

The regex-based splice has three failure modes: wrong indentation prefix (prepends `"    "` to a body that already has its own indentation), lookahead fails when no blank line separates methods, breaks on any helper method in the class. Fix: AST-based line replacement using `ast.parse` to locate exact line ranges of `load` and `predict`, then replace by line index in reverse order. Verify result with `ast.parse` before returning.

**Priority 4 — `_parse_methods` conflates methods (`agent.py`)**

Lookahead regex `(?=\ndef )` captures both methods as one block when no blank line separates them. Fix: split on `^def ` boundaries using `re.split(r"(?=^def )", raw, flags=re.MULTILINE)`, then match each block by its opening signature.

**Priority 5 — `write_scaffold` crashes on `None` fields (`writer.py`)**

After the inspector overhaul, `framework`, `class_name`, `input_hint`, `output_hint` can be `None`. The scaffold template formats them directly. Fix: coerce `None` to `"unknown"` before template formatting.

**Priority 6 — Stale temp dir across retries (`deploy.py`)**

The same `tmp_dir` is reused across all validation attempts. Stale module state can cause attempt 2 to pass and attempt 3 to fail with the same error as attempt 1. Fix: create a fresh subdirectory per attempt (`Path(tmp_root) / str(attempt)`).

### 8.3 — `--framework` and `--yes` flags

**`--framework`** (on `deploy`): optional hint that sets `raw_facts["framework_hint"]` as trusted input to the LLM interpretation stage. Does not skip structural extraction. If provided and confidence is otherwise sufficient, skips the clarifying question flow.

```bash
inference-engine deploy ./model.pt --framework pytorch
inference-engine deploy ./model.pkl --framework xgboost
```

**`--yes`** (on `deploy` and `fix`): explicit non-interactive flag. Skips all confirmation prompts and clarifying questions. Replaces the implicit `_is_interactive()` inference for CI use. All future commands must support `--yes` from the start — do not add new commands that rely solely on `_is_interactive()`.

```bash
inference-engine deploy ./model.pkl --name sentiment --version v1 \
  --device cpu --routing static --sample-input "great movie" --yes
```

### 8.4 — `sample_input` in generation and fix prompts

`sample_input` currently feeds only into validation. It must be included in all three LLM calls:

- **`generate()` prompt** — append `"Sample input: {sample_input!r}\npredict() must handle this exact input type."` This is the single cheapest improvement to codegen quality.
- **`fix()` prompt** — append metadata summary and `sample_input` so the LLM knows what input caused the failure, not just the traceback.
- **LLM interpretation prompt** — so the interpreter can infer `input_hint` from a concrete value when the inspector couldn't determine it.

### 8.5 — Tests

`tests/test_cli_phase8_inspector.py`:
- each extractor returns partial JSON on failure, never raises, always exits 0
- `TorchExtractor` correctly distinguishes state_dict from full model
- `OnnxExtractor` preserves `dim_param` for dynamic axes (not `0`)
- `DirectoryExtractor` reads `config.json` without loading weights
- confidence derivation: high when all fields known, low when errors present
- LLM interpretation prompt construction includes `raw_facts`, `sample_input`, `--framework` hint
- clarifying question flow patches metadata and re-runs interpretation (mock LLM)
- `--yes` skips clarifying questions

`tests/test_cli_phase8_fixes.py`:
- `_parse_sample_input`: numeric array, plain string, nested object, invalid JSON
- `_splice_methods`: helper method present, inconsistent indentation, no blank line between methods
- `_parse_methods`: no blank line between methods, trailing comment after predict
- `fix --sample-input` in non-interactive mode succeeds
- `write_scaffold` with all `None` metadata fields produces valid Python

### Deliverables
- Rewritten `app/cli/core/inspector.py` — layered extractors, always-exit-0 subprocess, `raw_facts` / `confidence` / `inspection_errors` on `ArtifactMetadata`
- Updated `app/cli/core/agent.py` — `interpret()` function, enriched `fix()` and `generate()` prompts with `sample_input` and metadata
- Updated `app/cli/commands/deploy.py` — `--framework`, `--yes`, interpretation step between inspection and codegen, fresh temp dir per retry
- Updated `app/cli/commands/fix.py` — `--sample-input`, `--yes`, AST-based `_splice_methods`
- Updated `app/cli/__main__.py` — new flags on both subcommands
- Updated `app/cli/core/writer.py` — `None`-safe scaffold formatting
- Updated `app/cli/core/prompts.py` — `sample_input` JSON parsing, `framework_hint` in `DeployAnswers`
- Two new test files

---

## Phase 9 — Deployment Packaging + Multi-Platform Export

*Proposal features: 1, 2*
*Estimated effort: 4–5 weeks*
*Prerequisite: Phase 8 revision complete. `deployment.json` is written from inspector metadata — it must be reliable before this phase begins.*

### Goal
Turn a deployed model into a portable artifact that can be shipped to any target environment without manual repackaging.

### 9.1 — Packaging generator (Proposal Feature 2)

New command:

```bash
inference-engine package models/sentiment/v1/
```

Generates in the model directory:

```
models/sentiment/v1/
├── definition.py          (existing)
├── Dockerfile             (generated from template)
├── requirements.txt       (generated — pinned from current venv)
└── deployment.json        (metadata: name, version, framework, load_format, device, created_at, sample_input)
```

`Dockerfile` is template-based, not LLM-generated. Parameterised by:
- Python version (read from `sys.version_info`)
- device: `cpu` uses `python:3.x-slim`, `gpu` uses `nvidia/cuda:12.x-runtime`
- port (default 8000, overridable with `--port`)

`requirements.txt` is generated by reading the framework from `deployment.json` and pinning the relevant packages from the current environment using `importlib.metadata.version()`. No LLM involved. Packages pinned per framework:

| Framework | Packages pinned |
|---|---|
| sklearn | `scikit-learn`, `joblib`, `numpy` |
| pytorch | `torch` |
| transformers | `transformers`, `torch`, `tokenizers` |
| xgboost | `xgboost`, `numpy` |
| lightgbm | `lightgbm`, `numpy` |
| catboost | `catboost`, `numpy` |
| onnx | `onnxruntime`, `numpy` |
| sentence_transformers | `sentence-transformers`, `torch` |

Plus `fastapi`, `uvicorn`, `inference-engine` itself always included.

`deployment.json` includes `sample_input` from `DeployAnswers` so downstream commands (`benchmark`, `snippets`, metadata API) can use it without requiring the user to re-specify it.

Implementation: `app/cli/commands/package.py` + `app/cli/core/packager.py` + `app/cli/core/templates/Dockerfile.cpu.j2` + `app/cli/core/templates/Dockerfile.gpu.j2`.

### 9.2 — Multi-platform export (Proposal Feature 1)

New command:

```bash
inference-engine export models/sentiment/v1/ --target sagemaker
```

Reads `deployment.json` for metadata. Fails with a clear message if `deployment.json` is absent (run `inference-engine package` first).

Supported targets:

**`sagemaker`**
```
export/sentiment-v1-sagemaker/
├── model.tar.gz           (artifact + inference.py, tarred for S3 upload)
└── inference.py           (model_fn loads via definition.py; predict_fn calls pipeline.run())
```
`inference.py` is template-based. `model_fn` imports `build_pipeline` from `definition.py` and calls `model.load()`. `predict_fn` deserialises the request body and calls `pipeline.run()`.

**`bentoml`**
```
export/sentiment-v1-bentoml/
├── service.py             (BentoML Service wrapping InferencePipeline.run())
├── bentofile.yaml         (includes python packages from deployment.json framework)
└── requirements.txt
```

**`ray`**
```
export/sentiment-v1-ray/
├── deployment.py          (Ray Serve Deployment; handle() calls pipeline.run())
└── requirements.txt
```

**`docker`** (standalone, no platform SDK)
```
export/sentiment-v1-docker/
├── Dockerfile             (same template as package command)
├── requirements.txt
└── serve.py               (minimal FastAPI app: POST /predict → pipeline.run())
```
`serve.py` is a ~30-line FastAPI app, not the full engine. It imports `build_pipeline` from `definition.py` and exposes a single `/predict` endpoint. No auth, no job queue — just the model.

The LLM is used only when the target format requires a calling convention that differs from `pipeline.run(x)` and the existing `predict()` body cannot be reused directly. In practice this is rare — all templates call `pipeline.run()` directly.

All exporters implement a common `BaseExporter` ABC:
```python
class BaseExporter(ABC):
    def export(self, model_dir: Path, output_dir: Path, deployment: dict) -> None: ...
```

Templates live in `app/cli/core/templates/<target>/`.

Implementation: `app/cli/commands/export.py` + `app/cli/core/exporters/` (base + 4 target exporters).

Note: Replicate export is deferred — see "What We Are Not Building."

### 9.3 — Tests

`tests/test_cli_phase9_package.py`:
- output file structure for cpu and gpu device
- `requirements.txt` contains correct pinned packages per framework
- `deployment.json` contains all required fields including `sample_input`
- Dockerfile uses correct base image per device
- fails gracefully when `definition.py` is absent

`tests/test_cli_phase9_export.py`:
- each exporter produces correct file structure (no real Docker build, just file assertions)
- `sagemaker` exporter: `inference.py` contains `model_fn` and `predict_fn`
- `docker` exporter: `serve.py` is valid Python with a `/predict` route
- fails with clear message when `deployment.json` is absent

### Deliverables
- `app/cli/commands/package.py`
- `app/cli/core/packager.py`
- `app/cli/commands/export.py`
- `app/cli/core/exporters/` (base + 4 target exporters: sagemaker, bentoml, ray, docker)
- `app/cli/core/templates/` (Dockerfile templates + per-target service templates)
- Two new test files

---

## Phase 10 — Developer Experience

*Proposal features: 7, 9, 10, 6*
*Estimated effort: 3–4 weeks*

### Goal
Reduce friction at every point where a developer interacts with the platform.

### 10.1 — Automatic sample payload inference (Proposal Feature 9)

The LLM interpretation stage (Phase 8) already receives `raw_facts` and `sample_input`. The interpretation call is extended to return a `suggested_sample_input` field alongside `framework` and `input_hint`. No separate rule-based logic is needed — the LLM infers the suggestion from the same facts it uses for interpretation.

The suggestion is shown as the default value in the `sample_input` prompt during interactive deploy:

```
? Sample input for validation: [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, ...]
  (suggested from n_features_in_=20)
```

The user can accept or override. In `--yes` mode, the suggestion is used automatically if no `--sample-input` flag was provided.

This collapses the original 10.1 rule-based suggestion logic into the Phase 8 interpretation call. No separate implementation needed beyond extending the interpretation response schema.

### 10.2 — Client SDK snippet generator (Proposal Feature 10)

New command:

```bash
inference-engine snippets sentiment:v1
inference-engine snippets sentiment:v1 --output snippets/
inference-engine snippets sentiment:v1 --host https://api.mycompany.com
```

Reads `deployment.json` for `sample_input`, `framework`, `name`, `version`. Fails with a clear message if `deployment.json` is absent.

Prints (or writes to `--output`) ready-to-use client code in three languages:

**curl**
```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"model": "sentiment", "version": "v1", "data": "great movie"}'
```

**Python** (httpx)
```python
import httpx
response = httpx.post(
    "http://localhost:8000/predict",
    headers={"X-API-Key": "<your-key>"},
    json={"model": "sentiment", "version": "v1", "data": "great movie"},
)
print(response.json())
```

**JavaScript** (fetch)
```javascript
const response = await fetch("http://localhost:8000/predict", {
  method: "POST",
  headers: {"X-API-Key": "<your-key>", "Content-Type": "application/json"},
  body: JSON.stringify({model: "sentiment", version: "v1", data: "great movie"}),
});
console.log(await response.json());
```

Templates are static with variable substitution. No LLM needed. `--host` defaults to `http://localhost:8000`.

Implementation: `app/cli/commands/snippets.py` (~60 lines, three string templates).

### 10.3 — Explain mode (Proposal Feature 7)

Add `--explain` flag to `inference-engine deploy`. After generation, before the preview, print a structured explanation block assembled from data already collected during the deploy flow — no extra LLM calls.

After Phase 8, the explanation block is significantly richer:

```
Inspector
  Format           pickle / XGBClassifier
  Confidence       medium (xgboost not installed, framework inferred from class name)
  Inspection errors  layer=deep: ModuleNotFoundError: No module named 'xgboost'

LLM Interpretation
  Framework        xgboost (inferred)
  Load format      joblib
  Input hint       numpy array or pandas DataFrame
  Clarifying Q     "Is this an XGBModel or a raw Booster?" → answered: XGBModel

Generation
  Attempt          1 (no repair needed)
  Model            llama-3.3-70b-versatile

Validation
  Result           passed
  Output           0.87
  Duration         34ms
```

Fields shown: format, confidence, inspection errors (if any), framework + how it was determined (rule vs LLM), whether a clarifying question was asked and what the answer was, generation attempt count, validation result and output value, validation duration.

Implementation: a `DeployTrace` dataclass populated throughout `run_deploy()`, printed at the end when `--explain` is set.

### 10.4 — Hot reload endpoint (Proposal Feature 6)

New admin endpoint:

```http
POST /admin/reload
```

Required scope: `admin`

Behaviour:
1. Calls `registry.clear_cache()` — evicts all loaded pipelines from the LRU cache
2. Re-runs `registry.warm_up()` — reloads all registered definitions from disk
3. Re-reads `app/config/routing.py` — picks up any routing changes written by `inference-engine deploy`
4. Returns `{"reloaded_models": ["sentiment:v1", ...], "routing_updated": true, "duration_ms": 142}`

`ModelRegistry.clear_cache()` evicts all entries from `self._cache` and resets the LRU order. `warm_up()` is already idempotent.

Routing reload: `importlib.reload` on the routing config module, then call `routing_service.update_routes(new_routes)`. `RoutingService` needs an `update_routes()` method that replaces `self.routes` atomically.

New route: `app/adapters/http/routes/admin.py` (extends the existing file which already has `reload_model` and `memory_status`).

### 10.5 — `fix --dry-run`

Add `--dry-run` to the `fix` subcommand. Prints the unified diff and exits without writing. Makes `fix` safe to run in CI for inspection purposes.

```bash
inference-engine fix models/sentiment/v1/ --sample-input "great movie" --dry-run
```

The diff display already exists in `run_fix()` — this is purely a flag that skips the write step and the confirmation prompt.

### Deliverables
- Extended LLM interpretation response schema with `suggested_sample_input` (Phase 8 extension, no new file)
- `app/cli/commands/snippets.py`
- `--explain` flag in `deploy.py` with `DeployTrace` dataclass
- `app/adapters/http/routes/admin.py` extended with `/admin/reload`
- `ModelRegistry.clear_cache()` method
- `RoutingService.update_routes()` method
- `--dry-run` flag on `fix` subcommand in `fix.py` and `__main__.py`
- Tests for each

---

## Phase 11 — Operational Maturity

*Proposal features: 8, 11, 12*
*Estimated effort: 2–3 weeks*

### Goal
Make the platform operationally observable and self-documenting.

### 11.1 — Benchmark CLI (Proposal Feature 11)

New command:

```bash
inference-engine benchmark sentiment:v1 \
  --host http://localhost:8000 \
  --n 200 \
  --concurrency 10 \
  --sample-input "great movie"
```

`--sample-input` is required. If absent and `deployment.json` exists in the model directory, reads `sample_input` from it. If neither is available, exits with a clear message.

`--host` defaults to `http://localhost:8000`. `--n` defaults to 100. `--concurrency` defaults to 1.

Uses `httpx.AsyncClient` with a semaphore for concurrency control. Sends all requests, collects latencies, computes statistics with `statistics` stdlib. No new dependencies.

Output:

```
Model:        sentiment:v1
Host:         http://localhost:8000
Requests:     200
Concurrency:  10
──────────────────────────────────
p50:          8ms
p95:          23ms
p99:          41ms
Throughput:   87 req/s
Errors:       0 (0.0%)
Cold start:   142ms (first request excluded from percentiles)
```

Errors are counted but do not abort the run. Error rate is shown. If error rate > 10%, a warning is printed.

Implementation: `app/cli/commands/benchmark.py` (~80 lines, pure httpx + statistics).

### 11.2 — Registry metadata API (Proposal Feature 12)

New endpoint:

```http
GET /models/{name}/{version}/metadata
```

Returns:

```json
{
  "name": "sentiment",
  "version": "v1",
  "framework": "sklearn",
  "load_format": "joblib",
  "device": "cpu",
  "input_hint": "raw text string",
  "output_hint": "integer class label",
  "sample_input": "great movie",
  "executor": "cpu",
  "routing_strategy": "static",
  "loaded": true,
  "artifact_size_mb": 2.1
}
```

Data sources, in priority order:
1. `deployment.json` in the model directory (written by `inference-engine package`) — provides `framework`, `load_format`, `device`, `input_hint`, `output_hint`, `sample_input`, `artifact_size_mb`
2. `ExecutionPolicy` config — provides `executor`
3. `RoutingService` config — provides `routing_strategy`
4. Registry cache state — provides `loaded`

Fields absent from `deployment.json` (i.e. `package` was not run) are returned as `null`. The endpoint does not fail if `deployment.json` is absent — it returns what it can.

New route: `app/adapters/http/routes/models.py` extended with the new path.

### 11.3 — Artifact fingerprinting + generation cache (Proposal Feature 8)

Cache LLM generation results to avoid redundant API calls on re-deploy of the same artifact.

Cache key is a SHA-256 hash of:
- artifact file bytes
- interpreted metadata JSON (from Stage 2 LLM interpretation) — captures user answers to clarifying questions
- prompt template version (a `PROMPT_VERSION` constant in `agent.py`, bumped manually when system prompts change)

This is more precise than the original plan's `SHA256(artifact) + framework + template_version`. Two deploys of the same artifact with different answers to clarifying questions (e.g. "state_dict" vs "full model") produce different cache keys and different cached code.

Cache stored at `~/.inference-engine/cache/<hash>.json`. Schema:
```json
{
  "key": "<sha256>",
  "load_body": "...",
  "predict_body": "...",
  "framework": "pytorch",
  "created_at": "2026-05-14T07:00:00Z",
  "prompt_version": "3"
}
```

On deploy, if a cache hit exists:
- interactive: `"Cached generation found (pytorch, created 2026-05-14). Use it? [Y/n]"`
- `--yes` mode: always use cache, print `"Using cached generation."`

Cache is never expired by time — artifacts are immutable. Invalidated only when `PROMPT_VERSION` changes (different key).

Implementation: `app/cli/core/cache.py` (~60 lines). Integrated into `run_deploy()` between the interpretation step and the `generate()` call.

### Deliverables
- `app/cli/commands/benchmark.py`
- Extended `app/adapters/http/routes/models.py` with metadata endpoint
- `app/cli/core/cache.py` integrated into deploy flow
- Tests: benchmark output format and error handling, metadata endpoint with and without `deployment.json`, cache hit/miss/invalidation on prompt version bump

---

## Roadmap Summary

| Phase | Status | Key deliverable | Effort |
|---|---|---|---|
| Pre | ✅ Complete | Async Postgres, shutdown safety, docs | — |
| 8 | ⚠️ Revision required | Inspector overhaul, CLI bug fixes, `--framework`, `--yes` | 3–4 weeks |
| 9 | Not started | `package` and `export` commands, 4 targets | 4–5 weeks |
| 10 | Not started | Snippets, explain mode, hot reload, `fix --dry-run` | 3–4 weeks |
| 11 | Not started | Benchmark CLI, metadata API, generation cache | 2–3 weeks |

Total remaining: **13–17 weeks** working at a steady pace.

---

## What We Are Not Building

- **Playground UI (Feature 5):** FastAPI's auto-generated `/docs` (Swagger UI) already provides interactive testing. A custom playground adds frontend complexity for marginal gain. Revisit if there is a specific use case Swagger doesn't cover.
- **Replicate export:** Replicate's format changes frequently and their target audience (hobbyist GPU hosting) doesn't align with the platform's production focus. Can be added later as a community contribution.
