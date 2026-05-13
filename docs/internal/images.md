# Documentation Images

All 18 images required across the documentation. Each entry includes the target file, a description of what the image communicates, and a detailed generation prompt — one for **light mode** (white/light-grey background) and one for **dark mode** (dark surface background).

Theme context for all images: **MkDocs Material**, primary color **indigo** (`#3f51b5`), supports light and dark mode. Diagrams must feel like they belong in Stripe, Linear, or Vercel docs — pixel-precise, zero decorative noise, clean sans-serif (Inter or equivalent), no drop shadows, no gradients.

**Color tokens used throughout:**

| Token | Light mode | Dark mode |
|---|---|---|
| Background | `#ffffff` | `#1a1a2e` |
| Surface / band fill | `#f0f2ff` / `#f8f9ff` | `#23234a` / `#1e1e3a` |
| Indigo accent | `#3f51b5` | `#7986cb` |
| Charcoal label | `#1a1a2e` | `#e8eaf6` |
| Subtitle / secondary | `#6b7280` | `#9fa8da` |
| Green | `#2e7d32` | `#66bb6a` |
| Amber | `#f59e0b` | `#ffca28` |
| Red | `#b71c1c` | `#ef5350` |
| Teal | `#00695c` | `#4db6ac` |

---

## 1. System Architecture — Layer Diagram

**Used in:** `concepts/architecture.md`, `README.md`

**Description:** Shows the six distinct code layers of the engine with their package paths, their allowed dependency directions, and the special `ExecutionPolicy` injection that wires the execution layer into the service layer without making it a peer of the other four vertical tiers. Must surface every invariant from `architecture.md`: no upward imports, no HTTP in domain/services, no storage SDKs in domain, and the `@lru_cache`/`Depends()` DI mechanism.

---

### Light Mode Prompt

Create a clean vertical layered architecture diagram for a Python ML inference backend. **White background** (`#ffffff`). Seven stacked horizontal bands in this order, top to bottom:

1. **HTTP Adapter** — package: `app/adapters/http/` — subtitle: `FastAPI routes · Pydantic schemas · Middleware · Depends()`
2. **Service Layer** — package: `app/services/` — subtitle: `PredictionService · AsyncInferenceService · RoutingService`
3. **Domain Layer** — package: `app/domain/` — subtitle: `ModelRegistry · InferencePipeline · Job · BaseModel/Preprocessor/Postprocessor/Validator`
4. **Infrastructure** — package: `app/infra/` — subtitle: `SQLiteJobStore · PostgresJobStore · ArqQueue · LocalModelLoader · S3ModelLoader`
5. **Config** — package: `app/config/` — subtitle: `routing.py · execution.py · sla.py` — thinner band, lighter fill

A sixth box labeled **Execution** (package: `app/execution/`) with subtitle `InferenceExecutor (ThreadPool) · OnnxExecutor (onnxruntime) · TritonExecutor (tritonclient gRPC)` sits **to the right** of the Service Layer band, connected by a **horizontal bidirectional arrow** labeled `injected via ExecutionPolicy` in italic grey. The Execution box has a **teal-tinted border** (`#00695c`) to distinguish it from the vertical stack.

A bold downward arrow runs along the **left edge** of the stack labeled `"dependencies flow downward only"` in small caps.

Two small annotation callouts in the lower-right corner:
- `"@lru_cache providers in deps.py"` pointing to the DI wiring between HTTP Adapter and Service
- `"lifespan hook: warm_up() + arq connect on startup"` pointing to the HTTP Adapter band

**Band fills:** alternate `#f0f2ff` and `#ffffff`. **Borders:** `#3f51b5` (1.5 px). **Labels:** `#1a1a2e` bold 13 px. **Subtitles:** `#6b7280` 11 px. **Arrow heads:** `#3f51b5`. Rounded rectangles (8 px radius). No drop shadows. Dimensions: **940×580px**.

---

### Dark Mode Prompt

Identical structure to the light mode version above. Replace:
- Background: `#1a1a2e`
- Band fills: alternate `#23234a` and `#1e1e3a`
- Band borders: `#7986cb`
- Labels: `#e8eaf6`
- Subtitles: `#9fa8da`
- Arrow heads: `#7986cb`
- Execution box teal border: `#4db6ac`
- Annotation text: `#b0bec5`

All text, layout, content, and dimensions identical to the light mode version. **940×580px**.

---

## 2. Synchronous Request Lifecycle — Sequence Diagram

**Used in:** `concepts/request-lifecycle.md`

**Description:** Traces a `POST /predict` request through every layer of the stack, showing the exact method names, the job state transitions (`PENDING → RUNNING → SUCCEEDED`), the timeout parameter, and all three rejection paths from the middleware stack. Every participant maps to a real class in the codebase.

---

### Light Mode Prompt

Create a horizontal swimlane sequence diagram. **White background.** Participants as vertical columns, left to right, with indigo (`#3f51b5`) header bars and white labels:

**Client | AuthMiddleware | RateLimitMiddleware | PayloadGuardMiddleware | PredictionService | RoutingService | JobService | InferenceExecutor | InferencePipeline**

Show these numbered sequential steps as horizontal arrows:

1. `Client → AuthMiddleware`: `POST /predict  {model, version, data}` — solid arrow
2. `AuthMiddleware → RateLimitMiddleware`: `identity validated` — solid arrow
3. `RateLimitMiddleware → PayloadGuardMiddleware`: `within limit` — solid arrow
4. `PayloadGuardMiddleware → PredictionService`: `PredictRequest(model, version, data)` — solid arrow
5. `PredictionService → RoutingService`: `resolve(model_name, version=None)` — solid arrow
6. `RoutingService → PredictionService`: `(model_name, "v1")  ← concrete version always resolved` — dashed return arrow
7. `PredictionService → JobService`: `create_job(model, version)` — solid arrow; **annotate return**: `Job(id=uuid, status=PENDING)`
8. `PredictionService → InferenceExecutor`: `submit(run_pipeline, timeout_s=SLA_TIMEOUT)` — solid arrow
9. `InferenceExecutor → JobService`: `mark_running(job_id)  → status: RUNNING` — solid arrow
10. `InferenceExecutor → InferencePipeline`: `pipeline.run(payload)` — solid arrow
11. `InferencePipeline → InferenceExecutor`: `result` — dashed return arrow
12. `InferenceExecutor → JobService`: `mark_succeeded(job_id, result)  → status: SUCCEEDED` — solid arrow
13. `InferenceExecutor → PredictionService`: `result` — dashed return arrow
14. `PredictionService → Client`: `HTTP 200  {"result": ..., "job_id": "..."}` — solid arrow

**Three rejection paths** — short red dashed arrows pointing back to Client:
- From `AuthMiddleware`: `Missing/unknown X-API-Key → 401`
- From `RateLimitMiddleware`: `Sliding window exceeded → 429`
- From `PayloadGuardMiddleware`: `Body > 1 MB → 413`

Annotate a box around steps 9–12 labeled `"runs in ThreadPoolExecutor worker thread"` with an amber dashed border.

Light grey alternating row bands for readability. Arrow labels in 10 px dark charcoal. Rejection arrows in red (`#b71c1c`). Dimensions: **1140×640px**.

---

### Dark Mode Prompt

Same structure and all step labels identical to the light mode version above. Replace:
- Background: `#1a1a2e`
- Participant header fill: `#3f51b5` → `#283593`; text: `#e8eaf6`
- Alternating row bands: `#1e1e3a` / `#23234a`
- Arrow heads and labels: `#9fa8da`
- ThreadPool annotation box: amber `#ffca28` dashed border
- Rejection arrows: `#ef5350`

All layout, participants, and step labels unchanged. **1140×640px**.

---

## 3. Asynchronous Request Lifecycle — Sequence Diagram

**Used in:** `concepts/request-lifecycle.md`

**Description:** Shows both async dispatch paths side by side — the Redis/arq path (separate worker process) and the in-process asyncio fallback — from `POST /predict/async` through to the poll `GET /predict/async/{job_id}`. Makes the `REDIS_URL` branch condition and the ArqWorker process boundary explicit.

---

### Light Mode Prompt

Create a sequence diagram split into **two parallel scenarios side by side**, separated by a vertical divider. Label the left half **"with Redis (REDIS_URL set)"** and the right half **"without Redis (asyncio fallback)"**.

**Left side — with Redis:**
Participants (vertical columns): `Client | AsyncInferenceService | JobService | ArqQueue | ArqWorker`

Steps:
1. `Client → AsyncInferenceService`: `POST /predict/async  {model, version, data}`
2. `AsyncInferenceService → JobService`: `create_job()` — return annotated: `Job(id=uuid, status=PENDING)`
3. `AsyncInferenceService → ArqQueue`: `enqueue_inference(job_id, model, version, payload)`  — annotated: `arq.enqueue_job()`
4. `AsyncInferenceService → Client`: `HTTP 202  {"job_id": "uuid"}` — immediate return
5. *(gap / async boundary)* `ArqWorker → JobService`: `mark_running(job_id)  → RUNNING`
6. `ArqWorker → InferencePipeline`: `pipeline.run(payload)`
7. `ArqWorker → JobService`: `mark_succeeded(job_id, result)  → SUCCEEDED`
8. *(later)* `Client → AsyncInferenceService`: `GET /predict/async/{job_id}`
9. `AsyncInferenceService → JobService`: `get_job(job_id)`
10. `AsyncInferenceService → Client`: `HTTP 200  {status: "succeeded", result: ...}`

Draw a **dashed box** around `ArqWorker` rows labeled `"separate arq worker process"`.

**Right side — without Redis:**
Participants: `Client | AsyncInferenceService | JobService | asyncio.Task`

Steps identical to left side except:
- Step 3 becomes: `AsyncInferenceService → asyncio.Task`: `asyncio.create_task(run_pipeline(job_id))` — annotated: `in-process coroutine`
- No separate process box; `asyncio.Task` is in the same process as `AsyncInferenceService`

A small label at the top of the right side: `"REDIS_URL not set — graceful fallback"`.

White background. Indigo participant headers on left; slightly lighter indigo on right. Dimensions: **1220×600px**.

---

### Dark Mode Prompt

Same structure and all step labels identical to the light mode version above. Replace:
- Background: `#1a1a2e`
- Participant headers: `#283593` (left), `#1a237e` (right)
- Row bands: `#1e1e3a` / `#23234a`
- Arrow labels: `#9fa8da`
- ArqWorker dashed box border: `#7986cb`

All layout and step labels unchanged. **1220×600px**.

---

## 4. Async Job State Machine

**Used in:** `concepts/async-jobs.md`

**Description:** State diagram for the `Job.status` field covering all six values — `CREATED`, `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED` — with every transition labeled by the exact method or event that triggers it, including the reaper path for stuck jobs (`> 10 min in RUNNING`).

---

### Light Mode Prompt

Create a finite state machine diagram. **White background.** Six states as rounded rectangles (12 px radius), with these fills:

- **CREATED** — fill `#f5f5f5`, border `#9e9e9e`
- **PENDING** — fill `#e8eaf6`, border `#3f51b5` (indigo)
- **RUNNING** — fill `#fff8e1`, border `#f59e0b` (amber; indicates active)
- **SUCCEEDED** — fill `#e8f5e9`, border `#2e7d32` (green); **double border** (terminal state)
- **FAILED** — fill `#ffebee`, border `#b71c1c` (red); **double border** (terminal state)
- **CANCELLED** — fill `#f5f5f5`, border `#9e9e9e`; **double border** (terminal state)

Layout: CREATED top-left, PENDING top-center, RUNNING center, SUCCEEDED bottom-right, FAILED bottom-left, CANCELLED bottom-center.

Transitions (labeled arrows):
- `CREATED → PENDING`: `"job enqueued (ArqQueue.enqueue_inference / asyncio.create_task)"`
- `PENDING → RUNNING`: `"worker picks up — mark_running(job_id)"`
- `RUNNING → SUCCEEDED`: `"pipeline.run() returns — mark_succeeded(job_id, result)"`
- `RUNNING → FAILED`: `"exception raised — mark_failed(job_id, error)"` — red arrow
- `PENDING → CANCELLED`: `"cancelled before worker pickup"` — grey arrow
- `RUNNING → FAILED` *(second arrow, dashed)*: `"reaper: stuck > 10 min in RUNNING"` — **orange** dashed arrow with a small 🕐 clock icon; label: `"stuck-job reaper"`

Initial state: filled black circle pointing to `CREATED`.

A small legend box bottom-right: `"solid arrow = normal transition | dashed orange = reaper | double border = terminal"`.

Dimensions: **840×500px**.

---

### Dark Mode Prompt

Same layout and all transition labels identical to the light mode version above. Replace:

- Background: `#1a1a2e`
- CREATED fill: `#2a2a2a`, border: `#757575`
- PENDING fill: `#1a237e`, border: `#7986cb`
- RUNNING fill: `#3e2700`, border: `#ffca28`
- SUCCEEDED fill: `#1b5e20`, border: `#66bb6a`
- FAILED fill: `#7f0000`, border: `#ef5350`
- CANCELLED fill: `#2a2a2a`, border: `#757575`
- Arrow labels: `#e8eaf6`
- Reaper arrow: `#ff9800` dashed

All layout and labels unchanged. **840×500px**.

---

## 5. Inference Pipeline — Data Flow Diagram

**Used in:** `concepts/inference-pipeline.md`

**Description:** Shows the four pipeline stages as a horizontal chain with the exact base class method signatures and the data types flowing between each stage. The `Validator` is optional; `NoOpValidator` is the bypass. Each stage is a separate class implementing a specific base class interface.

---

### Light Mode Prompt

Create a horizontal pipeline flow diagram. **White background.** Four processing boxes connected by labeled arrows, left to right:

1. **Preprocessor** — `BasePreprocessor` — method: `transform(raw_input: Any) → model_input`
2. **Validator** — `BaseValidator` — method: `validate(model_input) → model_input` — **dashed border** and a tag `"optional (NoOpValidator = passthrough)"`
3. **Model** — `BaseModel` — method: `predict(model_input) → raw_output`
4. **Postprocessor** — `BasePostprocessor` — method: `transform(raw_output: Any) → response`

Arrows between boxes labeled with data types (italic grey):
- Left of box 1 ← incoming arrow labeled: `"raw JSON input (PredictRequest.data)"`
- Box 1 → Box 2: `"model-ready format"`
- Box 2 → Box 3: `"validated input"`
- A thin grey **bypass arc** over Box 2 labeled: `"NoOpValidator: passes through unchanged"`
- Box 3 → Box 4: `"raw model output"`
- Box 4 → right: `"response-ready result"` going into a box labeled `"PredictResponse.result"`

Above the full chain, a note: `"InferencePipeline.run(payload) orchestrates all four stages in sequence"`.

Each box: rounded rectangle, `#3f51b5` border, `#f0f2ff` fill. Validator box dashed border, `#f8f9ff` fill. Labels: `#1a1a2e` bold. Method signatures: `#3f51b5` monospace 10 px. Data-type arrow labels: `#6b7280` italic. Dimensions: **1040×300px**.

---

### Dark Mode Prompt

Same layout and labels as light mode. Replace:
- Background: `#1a1a2e`
- Box fill: `#23234a`; Validator fill: `#1e1e3a`
- Box borders: `#7986cb`; Validator border: `#7986cb` dashed
- Labels: `#e8eaf6`
- Method signatures: `#9fa8da`
- Arrow labels: `#b0bec5`

All layout and content unchanged. **1040×300px**.

---

## 6. Model Registry — Cache Lifecycle Diagram

**Used in:** `concepts/model-registry.md`

**Description:** Illustrates exactly what `ModelRegistry.get(name, version)` does — LRU cache lookup, per-key lock acquisition, `build_pipeline()` call which calls `model.load()` from the loader, caching the result, and LRU eviction when `max_loaded` is exceeded. The `warm_up()` eager-load path at startup is also shown.

---

### Light Mode Prompt

Create a flowchart diagram. **White background.** Start node: `"registry.get(name, version)"`.

**Main flow (left column):**

Decision diamond 1: `"In LRU cache? (keyed on name:version)"`
- **YES →** (green path, label `"cache hit"`) → `"Return cached InferencePipeline"` (green box) → End
- **NO →** continue down (indigo path, label `"cache miss"`)

Process: `"Acquire per-key threading.Lock()"`
Process: `"Call build_pipeline(name, version)"`
  - Sub-box (indented): `"loader.load(artifact_path) → artifact"` — loader is `LocalModelLoader` or `S3ModelLoader`
  - Sub-box (indented): `"definition.build_pipeline(artifact) → InferencePipeline"`
Process: `"Store pipeline in LRU cache"`

Decision diamond 2: `"len(cache) > max_loaded?"`
- **YES →** (amber path) `"Evict least-recently-used entry"` → `"Return pipeline"` → End
- **NO →** `"Return pipeline"` → End

**Startup path (right column, connected by dotted line):**
A separate box: `"lifespan hook: warm_up()"` with sub-label `"called once on uvicorn startup"`.
Arrow from this box pointing into `"Call build_pipeline()"` step, labeled `"eager-loads all configured models, fills cache before first request"`.

Colors: green cache-hit path, indigo main path, amber eviction branch. Rounded rectangles, diamond shapes. Dimensions: **940×560px**.

---

### Dark Mode Prompt

Same structure and all labels identical to light mode. Replace all backgrounds, fills, and text colors using the dark mode token table at the top of this document. Arrow heads and decision borders use `#7986cb`. Green path: `#66bb6a`. Amber path: `#ffca28`. **940×560px**.

---

## 7. Routing Strategies — Traffic Split Diagram

**Used in:** `concepts/routing.md`, `guides/configuring-routing.md`

**Description:** Three-panel side-by-side showing `static`, `canary`, and `ab` routing strategies exactly as implemented in `app/config/routing.py`. The canary uses `random.randint` (non-deterministic). The A/B strategy hashes the `X-Request-ID` header with SHA-256 to pick a version deterministically.

---

### Light Mode Prompt

Create a three-panel diagram on a **white background**, panels arranged horizontally with clear bold titles and a light grey divider between each.

**Panel 1 — Static:**
Title: `"static"`. A single solid indigo arrow from a `"Request"` box → `"v1 (100%)"` box. Below: small note `"version pinned in routing.py — no randomness"`.

**Panel 2 — Canary:**
Title: `"canary"`. A `"Request"` box feeds into a small fork node. From the fork:
- Thick indigo arrow (90% line weight) → `"v1 (primary  90%)"` box
- Thin lighter-indigo arrow (10% line weight) → `"v2 (canary  10%)"` box
A small annotation: `"random.randint(1, 100) — non-deterministic; same request-ID may hit either version"`.

**Panel 3 — A/B:**
Title: `"ab"`. A `"Request"` box → grey diamond/box labeled `"SHA-256(X-Request-ID) % 100"` → fork:
- 70% → `"v1"` box (indigo)
- 30% → `"v2"` box (lighter indigo / purple tint)
A small annotation: `"deterministic: same X-Request-ID always routes to same version"`.

Line thickness in Panel 2 visually encodes the split weight. SHA-256 hash box has a `#e0e0e0` fill and monospace label. All three panels share the same vertical height. Dimensions: **1120×360px**.

---

### Dark Mode Prompt

Same three-panel structure and all labels identical to light mode. Replace:
- Background: `#1a1a2e`; Panel dividers: `#3a3a6a`
- Request/version boxes: fill `#23234a`, border `#7986cb`
- SHA-256 box: fill `#2a2a4a`, text `#b0bec5`
- Arrow heads: `#7986cb` (primary) and `#5c6bc0` (secondary)
- Annotation text: `#9fa8da`

All layout and labels unchanged. **1120×360px**.

---

## 8. Execution Backends — Policy Resolution Diagram

**Used in:** `concepts/execution-backends.md`

**Description:** Shows how `ExecutionPolicy` (from `app/config/execution.py`) maps a `(model_name, version)` key to a specific executor instance. The dict is consulted first; any unmatched key falls back to the configured default executor. All four real executor types are shown.

---

### Light Mode Prompt

Create a mapping/routing diagram with three columns. **White background.**

**Left column — Requests (indigo-bordered boxes):**
- `echo:v1`
- `echo:v2`
- `my_model:v1`
- `(any other model:version)`

**Middle column — `ExecutionPolicy`:**
A single larger box labeled `"ExecutionPolicy"` with subtitle `"app/config/execution.py"` and internal pseudo-code: `"policy: dict[(name, version), executor]"` and `"default: InferenceExecutor"`. All left-column boxes point into this middle box.

**Right column — Executor instances (teal-bordered boxes):**
- `gpu_executor` — `InferenceExecutor` — `"max_workers=2, device=cuda"`
- `cpu_executor` — `InferenceExecutor` — `"max_workers=8, device=cpu"`
- `onnx_executor` — `OnnxExecutor` — `"onnxruntime · max_workers=4"`
- `triton_executor` — `TritonExecutor` — `"tritonclient gRPC · max_workers=8"`

Arrows from `ExecutionPolicy` to executors:
- `echo:v1` → `gpu_executor` — solid indigo
- `echo:v2` → `cpu_executor` — solid indigo
- `my_model:v1` → `onnx_executor` — solid indigo
- `(any other)` → `cpu_executor` — **grey dashed** arrow labeled `"default fallback"`

Small note: `"ExecutionPolicy.resolve(name, version) — O(1) dict lookup"`.

Dimensions: **940×440px**.

---

### Dark Mode Prompt

Same structure and labels as light mode. Replace all colors per dark mode token table. ExecutionPolicy box fill: `#23234a`. Executor boxes fill: `#1b3a38`, border: `#4db6ac`. Default dashed arrow: `#757575`. **940×440px**.

---

## 9. CLI Deploy — Flowchart

**Used in:** `cli/deploy.md`

**Description:** Full flowchart of `inference-engine deploy <artifact>` including the pickle safety warning, isolated subprocess inspection, LLM code generation loop (up to 3 attempts with traceback feedback), scaffold fallback on exhaustion, `--dry-run` early exit, and the three files written on success (`definition.py`, artifact copy, `routing.py` patch).

---

### Light Mode Prompt

Create a detailed vertical flowchart. **White background.** Steps top to bottom:

1. **Start:** `inference-engine deploy <artifact>` (rounded pill, indigo fill, white label)
2. **Process:** `"Show pickle safety warning"` → user types `"yes"` to continue. (If user declines → `"Exit 1"` red pill on right)
3. **Process:** `"Inspect artifact in isolated subprocess"` — sub-label: `"detect framework (pkl/onnx/torch) · extract input/output shapes · read metadata"`
4. **Decision diamond:** `"All --flags provided? (--name, --version, --device, --routing, --sample-input)"`
   - YES → skip to step 6
   - NO → **Process:** `"Interactive prompts for missing flags"`
5. **Process:** `"Send artifact metadata + sample-input + system prompt to LLM (Groq API)"` — generates `load()` and `predict()` for `definition.py`
6. **Process:** `"Validate generated pipeline in temp directory against sample-input"` — sub-label: `"imports definition.py, runs build_pipeline(), calls pipeline.run(sample_input)"`
7. **Decision diamond:** `"Validation passed?"`
   - YES → continue to step 9
   - NO → **Process:** `"attempt += 1"` → **Decision diamond:** `"attempt < 3?"`
     - YES → **Process:** `"Send traceback + previous code to LLM for fix"` → back to step 6 (dashed red back-arrow labeled `"retry"`)
     - NO → **Process:** `"Write scaffold definition.py with # TODO comments"` (amber box) → continue to step 9
8. **Decision diamond:** `"--dry-run flag?"`
   - YES → `"Print diff summary, exit 0 — no files written"` (grey dashed box, right side exit)
   - NO → continue
9. **Process:** `"Show file write preview + prompt user to confirm"`
10. **Process:** `"Write models/<name>/<version>/definition.py"` + `"Copy artifact to models/<name>/<version>/"` + `"Patch app/config/routing.py with new route entry"` (three parallel mini-boxes)
11. **End:** `"Print ready-to-use curl command"` (green pill)

Color coding: **green** success path/end, **red** rejection/retry paths, **amber** scaffold fallback, **grey dashed** dry-run exit. Indigo main path arrows. Dimensions: **820×1060px**.

---

### Dark Mode Prompt

Same structure and all step labels identical to light mode. Replace all backgrounds and colors per dark mode token table. Start/end pill: `#283593`/`#1b5e20`. Retry arrows: `#ef5350`. Scaffold box: `#3e2700` fill, `#ffca28` border. Dry-run box: `#2a2a2a` fill, `#757575` dashed border. **820×1060px**.

---

## 10. CLI Fix — Retry Loop Flowchart

**Used in:** `cli/fix.md`, `guides/fixing-a-broken-deployment.md`

**Description:** Flowchart of `inference-engine fix <model-dir>` including the validate → fail → LLM fix → re-validate loop (max 3 attempts), the safety constraint that only `load()` and `predict()` are rewritten (not `MODEL_NAME`, `MODEL_VERSION`, or `build_pipeline` structure), and both exit conditions (success with diff confirmation, failure with original file unchanged).

---

### Light Mode Prompt

Create a compact vertical flowchart. **White background.**

1. **Start:** `inference-engine fix models/<name>/<version>/` (indigo pill)
2. **Process:** `"Read existing definition.py"`
3. **Process:** `"Prompt user for sample_input (or use --sample-input flag)"`
4. **Process:** `"Validate existing pipeline against sample_input"` — sub-label: `"build_pipeline() → pipeline.run(sample_input)"`
5. **Decision:** `"Validation passed?"`
   - YES → `"Nothing to fix — report OK"` (green box) → **End (green)**
   - NO → continue
6. **Process:** `"Send error traceback + current load() + current predict() to LLM"`
7. **Process:** `"Apply LLM-generated fix to load() and predict() only"` — annotated note box to the right: `"MODEL_NAME, MODEL_VERSION, build_pipeline() structure NEVER modified"`
8. **Process:** `"Re-validate fixed code in temp directory"`
9. **Decision:** `"Validation passed?"`
   - YES → `"Show unified diff → user confirms"` → `"Atomically write fixed definition.py"` → **End (green)**
   - NO → `"attempt += 1"` → **Decision:** `"attempt < 3?"`
     - YES → (dashed back-arrow) → back to step 6, labeled `"retry with traceback"`
     - NO → `"Exit — original file unchanged"` (red box) → **End (red)**

Retry back-arrow is dashed red running on the right margin. Note box at step 7 has amber dashed border. Green paths, red exit, indigo main loop. Dimensions: **720×860px**.

---

### Dark Mode Prompt

Same structure and all labels as light mode. Replace all colors per dark mode token table. Safety note box: `#3e2700` fill, `#ffca28` dashed border. **720×860px**.

---

## 11. Security — Request Filtering Funnel

**Used in:** `concepts/security-model.md`

**Description:** Four-stage funnel showing what each middleware layer checks, what it passes, and what it rejects with the exact HTTP status code. The scope check is inside the route handler (not a middleware), so the funnel tightens once more before execution.

---

### Light Mode Prompt

Create a vertical funnel/filter diagram. **White background.** Four horizontal bands stacked vertically, each narrower than the one above, creating a visual funnel. Rejected requests exit as red arrows to the **right** of each band.

**Band 1 — `AuthMiddleware`** (widest):
- Left label: `"AuthMiddleware (app/adapters/http/middleware.py)"`
- Passes: `"valid X-API-Key header — identity resolved to tenant"`
- Rejects → right: `"Missing X-API-Key → HTTP 401"` and `"Unknown/invalid key → HTTP 401"` (two red arrows)

**Band 2 — `RateLimitMiddleware`** (slightly narrower):
- Left label: `"RateLimitMiddleware"`
- Passes: `"request count within per-tenant sliding window"`
- Rejects → right: `"Window exceeded → HTTP 429"`

**Band 3 — `PayloadGuardMiddleware`** (narrower still):
- Left label: `"PayloadGuardMiddleware"`
- Passes: `"Content-Length ≤ 1 MB"`
- Rejects → right: `"Body > 1 MB → HTTP 413"`

**Band 4 — Route Handler scope check** (narrowest):
- Left label: `"Route Handler (scope check)"`
- Passes: `"API key has required scope for this endpoint"`
- Rejects → right: `"Insufficient scope → HTTP 403"`

**Bottom — `"✓ Valid request reaches PredictionService"` in green.**

Band fills: `#f0f2ff` with `#3f51b5` left border (3 px). Rejection arrows: `#b71c1c` with HTTP status labels. Funnel narrows ~8% per stage. Dimensions: **820×580px**.

---

### Dark Mode Prompt

Same structure and all labels identical. Replace:
- Background: `#1a1a2e`
- Band fills: `#23234a`, left border: `#7986cb`
- Rejection arrows and labels: `#ef5350`
- Pass text: `#9fa8da`
- Bottom green text: `#66bb6a`

**820×580px**.

---

## 12. Production Deployment Topology

**Used in:** `guides/production-deployment.md`

**Description:** Infrastructure diagram showing the full production topology: nginx TLS termination and `X-Request-ID` injection, multiple uvicorn workers, multiple arq worker processes (each with their own in-process model cache), Redis (job queue + rate limit token store), Postgres (durable job store), and the model artifact store (local disk or S3). Shows which components read model artifacts.

---

### Light Mode Prompt

Create a production infrastructure topology diagram. **White background.**

**Tier 1 (top):** `"Client"` box (grey border).

**Arrow:** HTTPS → 

**Tier 2 — Edge:** `"nginx / Load Balancer"` box — subtitle: `"TLS termination · injects X-Request-ID header · reverse proxy"`

**Arrow:** HTTP/1.1 (proxy_pass) →

**Tier 3 — Application (two boxes side by side):**
- `"uvicorn workers  (×N)"` — subtitle: `"app.adapters.http.app:app --reload · port 8000 · API serving · model cache (warm_up at startup)"`  — indigo fill `#e8eaf6`
- `"arq workers  (×M)"` — subtitle: `"app.infra.queue.worker.WorkerSettings · async job execution · separate process · own model cache"` — dashed border (separate process), indigo fill

**Tier 4 — Data (two boxes side by side):**
- `"Redis  (redis:7-alpine)"` — subtitle: `"arq job queue · rate limit token store"` — teal fill `#e0f2f1`
- `"Postgres  (postgres:16-alpine)"` — subtitle: `"durable job store · jobs table · schema_migrations"` — teal fill

**Tier 5 — Storage:**
- `"model_artifacts/"` — subtitle: `"local disk (LocalModelLoader) OR s3://bucket (S3ModelLoader · boto3)"` — grey fill

Connections with labeled directional arrows:
- Client ↔ nginx: `HTTPS`
- nginx → uvicorn workers: `HTTP proxy_pass`
- uvicorn workers ↔ Redis: `rate limit check + job enqueue`
- uvicorn workers ↔ Postgres: `job reads/writes (asyncpg)`
- arq workers ↔ Redis: `job dequeue (arq)`
- arq workers ↔ Postgres: `job status updates`
- arq workers → model_artifacts/: `load artifact on first run`
- uvicorn workers → model_artifacts/: `warm_up() on startup`

Dashed border around arq workers labeled `"separate OS process"`. Dimensions: **940×640px**.

---

### Dark Mode Prompt

Same structure and all labels identical. Replace all fills and colors per dark mode token table. Teal data tier fill: `#1b3a38`. arq worker dashed border: `#7986cb`. **940×640px**.

---

## 13. Triton — Local vs. Remote Split Diagram

**Used in:** `integrations/triton.md`

**Description:** Shows exactly what code runs inside the Inference Engine process and what is delegated over gRPC to the Triton server. The Preprocessor and Validator run locally; `TritonExecutor.submit()` is the boundary; Triton runs model inference on its own model repository. The postprocessor runs locally again after the gRPC response returns.

---

### Light Mode Prompt

Create a two-zone diagram separated by a **bold vertical dashed line** (`#3f51b5`). **White background.**

**Left zone — `"Inference Engine Process"` (indigo tint background `#f0f2ff`):**
Vertical flow with continuous left-side arrow:
1. `"Preprocessor.transform()"` — sub-label: `"BasePreprocessor · raw input → model-ready tensor"`
2. `"Validator.validate()"` — dashed border, sub-label: `"optional · BaseValidator · NoOpValidator if none configured"`
3. `"TritonExecutor.submit()"` — bold border — sub-label: `"constructs InferRequest, calls tritonclient.grpc.InferenceServerClient.infer()"` — **this is the boundary crossing point**

**Right zone — `"Triton Inference Server"` (teal tint background `#e0f2f1`):**
Vertical flow:
1. `"Triton gRPC endpoint  :8001"` — receives `InferRequest`
2. `"Model Repository"` — sub-label: `"loads model backend (TensorRT / ONNX / PyTorch backend)"`
3. `"model inference runs on Triton"` — sub-label: `"returns InferResult over gRPC"`

**Boundary crossing arrows (horizontal, crossing the dashed line):**
- → `"gRPC call  (tritonclient.grpc)  →"` in bold indigo
- ← `"InferResult  ←"` in grey dashed

**Below the two zones (back in left zone):**
4. `"Postprocessor.transform()"` — sub-label: `"raw Triton output → PredictResponse.result"`

Full vertical flow arrow on left connects pre → validate → [gRPC] → post. Dimensions: **1020×460px**.

---

### Dark Mode Prompt

Same structure and all labels. Left zone background: `#1a1e38`. Right zone background: `#0d2b28`. Dashed divider: `#7986cb`. Text: `#e8eaf6`. gRPC arrow: `#7986cb` bold. Return arrow: `#9fa8da` dashed. **1020×460px**.

---

## 14. Docker / dev.sh Startup Sequence

**Used in:** `integrations/docker.md`, `quickstart/docker-quickstart.md`

**Description:** Ordered sequence showing the five steps `dev.sh` performs: (1) `docker compose up` for Postgres and Redis in parallel, (2) health-check loop waiting for Postgres, (3) DB migration creating `jobs` table and `schema_migrations`, (4) arq worker launched in background, (5) uvicorn launched in foreground. Steps 4 and 5 run indefinitely.

---

### Light Mode Prompt

Create a vertical timeline/Gantt-style sequence diagram. **White background.** A vertical `"time"` axis on the left with a downward arrow. Five horizontal process bars stacked vertically:

**Step 1 — `docker compose up`** (indigo bar):
- Label: `"docker compose up -d"`
- Two sub-bars side by side: `"postgres:16-alpine"` and `"redis:7-alpine"` starting simultaneously

**Step 2 — Health check loop** (amber bar):
- Label: `"wait-for-postgres loop"` with a small retry arc icon
- Sub-label: `"pg_isready · retries every 1s until healthy · exits loop on success"`
- Shown as a looping/cycling bar, not straight

**Step 3 — DB Migration** (indigo bar, short):
- Label: `"python scripts/migrate.py"`
- Sub-label: `"CREATE TABLE jobs (...) · CREATE TABLE schema_migrations · idempotent"`

**Step 4 — arq worker** (green bar, starts after step 3, **open-ended extending right**):
- Label: `"arq app.infra.queue.worker.WorkerSettings &"`
- Sub-label: `"background process · handles async job execution"`
- The bar has an open right end (arrow) labeled `"running indefinitely"`

**Step 5 — uvicorn** (indigo bar, starts after step 4, **open-ended extending right**):
- Label: `"uvicorn app.adapters.http.app:app --reload"`
- Sub-label: `"foreground process · serves HTTP on port 8000"`
- Open-ended bar labeled `"serving requests"`

Small green `"✓ healthy"` marker at the end of the health-check step. Amber retry arc in step 2. Dimensions: **940×480px**.

---

### Dark Mode Prompt

Same structure and all labels. Replace all colors per dark mode token table. Health-check bar: `#3e2700` fill, `#ffca28` border. Healthy marker: `#66bb6a`. arq bar: `#1b5e20`. uvicorn bar: `#283593`. **940×480px**.

---

## 15. Storage Backend — Decision Tree

**Used in:** `configuration/storage.md`

**Description:** Decision tree for both auto-selection choices: Job Store (Postgres when `DATABASE_URL` is set, SQLite otherwise) and Artifact Loader (local vs. S3 based on the artifact path). Shows connection pool config, file paths, and the `pip install boto3` requirement.

---

### Light Mode Prompt

Create a clean decision tree diagram with **two independent trees side by side**. **White background.** Diamond decision nodes (indigo `#3f51b5` fill, white text). Rounded rectangle result nodes.

**Left tree — Job Store selection:**
Root diamond: `"DATABASE_URL env var set?"`
- **YES →** `"PostgresJobStore"` (green box) — sub-label: `"asyncpg driver · min_size=1, max_size=10 connection pool · schema auto-created on startup"`
- **NO →** `"SQLiteJobStore"` (indigo box) — sub-label: `"file: app/instance/jobs.db · WAL journal mode · created automatically, zero config"`

Below PostgresJobStore: small note box: `"Recommended for production (concurrent writes, durability)"`
Below SQLiteJobStore: small note box: `"Default — works out of the box for local dev and zero-dependency quickstart"`

**Right tree — Artifact Loader selection:**
Root diamond: `"Artifact path format?"`
- **`s3://...`** → `"S3ModelLoader"` (teal box) — sub-label: `"boto3 · downloads to temp dir on first load · requires: pip install boto3"`
- **local path** → `"LocalModelLoader"` (indigo box) — sub-label: `"root: model_artifacts/ · direct disk read"`

Below S3ModelLoader: small note box: `"AWS credentials via env vars or IAM role"`

Both trees share identical diamond and result node styles. A bold horizontal label separates them: `"Job Store"` (left) and `"Artifact Loader"` (right). Dimensions: **940×440px**.

---

### Dark Mode Prompt

Same structure. Replace decision diamond fill: `#283593`. PostgresJobStore fill: `#1b5e20`. SQLite/Local fill: `#1a237e`. S3 fill: `#00695c`. Note boxes: `#23234a`. Text: `#e8eaf6`. Subtitles: `#9fa8da`. **940×440px**.

---

## 16. Project Structure — Layer Dependency Diagram

**Used in:** `development/project-structure.md`

**Description:** Six package bands with allowed import arrows (green, downward only) and explicitly forbidden import arrows (red, crossed out) with the reason for each prohibition. Matches the invariants from `architecture.md` exactly.

---

### Light Mode Prompt

Create a layered dependency diagram. **White background.** Six packages as stacked horizontal bands:

1. **`app/adapters/http/`** — `"FastAPI routes · Middleware · Pydantic schemas · Depends() DI"`
2. **`app/services/`** — `"PredictionService · AsyncInferenceService · RoutingService · JobService"`
3. **`app/domain/`** — `"ModelRegistry · InferencePipeline · Job · BaseModel · BasePreprocessor · BaseValidator · BasePostprocessor"`
4. **`app/infra/`** — `"SQLiteJobStore · PostgresJobStore · ArqQueue · LocalModelLoader · S3ModelLoader — implements domain interfaces"`
5. **`app/execution/`** — `"InferenceExecutor (ThreadPool) · OnnxExecutor · TritonExecutor"`
6. **`app/config/`** — `"routing.py · execution.py · sla.py — read by all layers"`

**Allowed arrows (solid green `#2e7d32`, downward):**
- adapters/http → services
- services → domain
- services → execution *(horizontal — execution injected via ExecutionPolicy)*
- infra → domain *(infra implements domain interfaces; domain does NOT import infra)*
- adapters/http → config, services → config, domain → config, infra → config, execution → config *(all read config)*

**Forbidden arrows (solid red `#b71c1c`, with a bold ✗ and reason label):**
- `domain ✗ services` — `"would invert dependency"`
- `services ✗ adapters` — `"no HTTP types in business logic"`
- `domain ✗ infra` — `"no storage SDKs (psycopg2/boto3) in domain"`

A **legend** box bottom-right: `"→ green = allowed import | ✗ red = forbidden | all deps flow downward only"`.

Band fills: alternating `#f0f2ff` / `#ffffff`. Borders: `#3f51b5`. Dimensions: **820×600px**.

---

### Dark Mode Prompt

Same structure. Replace fills: alternating `#23234a` / `#1e1e3a`. Borders: `#7986cb`. Green arrows: `#66bb6a`. Red forbidden arrows: `#ef5350`. Text: `#e8eaf6`. **820×600px**.

---

## 17. Grafana Dashboard — Panel Layout Mockup

**Used in:** `observability/monitoring.md`

**Description:** Mockup of a Grafana dashboard showing five recommended panels with realistic synthetic data. Helps operators know exactly what to build before they open Grafana.

---

### Light Mode Prompt

Create a Grafana dashboard mockup with a **light grey background** (`#f4f5f7`, matching Grafana's light theme). Five panels in a 2-2-1 grid (2 top, 2 middle, 1 bottom spanning full width). Panel fills: white `#ffffff`, border: `#e0e0e0`, panel title: dark `#1a1a2e`.

**Panel 1 (top-left) — Request Rate:**
Time-series line chart. Title: `"Request Rate by Model"`. Two lines: `"echo:v1"` (indigo `#3f51b5`, ~50 req/s) and `"echo:v2"` (lighter indigo `#7986cb`, ~15 req/s). Y-axis label: `"req/s"`. Smooth sinusoidal variation.

**Panel 2 (top-right) — Latency Percentiles:**
Time-series. Title: `"Inference Latency (ms)"`. Three lines: `p50` (green `#2e7d32`, ~20 ms), `p95` (amber `#f59e0b`, ~80 ms), `p99` (red `#b71c1c`, ~200 ms). Y-axis: `"ms"`.

**Panel 3 (middle-left) — Error Rate:**
Time-series. Title: `"Error Rate by Type"`. Lines for `timeout` (red), `model_not_found` (amber), `inference_error` (orange). Mostly near zero, occasional spikes to ~5%.

**Panel 4 (middle-right) — Job Queue Depth:**
Area chart. Title: `"Job Queue Depth (arq)"`. Single indigo area fill. Near-zero baseline, one spike to ~40 jobs, recovery back to zero. Y-axis: `"pending jobs"`.

**Panel 5 (bottom, full width) — Executor Inflight:**
Two stat/gauge panels side by side: `"cpu inflight  3/8 workers"` (indigo semicircle gauge) and `"gpu inflight  1/2 workers"` (teal semicircle). Below them, a combined time-series of inflight count over time.

Top bar: Grafana-style chrome showing dashboard name `"Inference Engine"` and time range picker `"Last 1h"`. Dimensions: **1220×740px**.

---

### Dark Mode Prompt

Same five panels and all labels. Replace background with `#161719` (Grafana dark theme). Panel fills: `#1f2023`, border: `#2a2a2e`. Panel titles: `#d8d9da`. Grid lines: `#2e2e32`. All chart line colors identical. Top chrome: `#111217`. **1220×740px**.

---

## 18. Metrics — Queue Depth Health vs. Overload

**Used in:** `observability/metrics.md`

**Description:** Annotated time-series graph of `job_queue_depth` over 30 minutes showing three phases — healthy (workers keeping up), overloaded (queue growing), and recovery (backlog draining) — with a dashed alert threshold line at depth 100. Helps operators recognize the signal before an incident.

---

### Light Mode Prompt

Create an annotated time-series graph. **White background.** X-axis: `"Time (minutes)"` 0–30. Y-axis: `"pending jobs"` 0–150.

**Three background phase zones:**
- **Phase 1 (0–10 min):** Very light green tint `#f1f8f1` background. Queue depth line stays flat near 0–5 jobs. Callout box annotation: `"✓ Healthy — arq workers keeping up with demand"`
- **Phase 2 (10–18 min):** Very light red tint `#fff5f5`. Queue depth rises steeply from 5 → ~120. Callout annotation: `"⚠ Overloaded — workers not keeping pace; scale arq workers or raise max_jobs per worker"`
- **Phase 3 (18–30 min):** Very light amber tint `#fffbf0`. Queue depth drops from 120 → ~0. Callout annotation: `"↓ Recovery — backlog draining as workers catch up"`

**Overlaid elements:**
- Indigo line (`#3f51b5`, 2.5 px) for the queue depth metric — `job_queue_depth`
- Horizontal **dashed red line** at y=100 labeled `"alert threshold (job_queue_depth > 100)"` — label in red to the right of the line
- Phase region boundaries marked by thin vertical dashed grey lines

Annotation callout boxes have a small pointer arrow pointing at the relevant section of the line. Axis labels: `#1a1a2e`. Grid lines: `#e0e0e0` light. Dimensions: **920×400px**.

---

### Dark Mode Prompt

Same graph structure and all labels identical to light mode. Replace:
- Background: `#1a1a2e`
- Phase 1 tint: `#0d1f0d`
- Phase 2 tint: `#1f0d0d`
- Phase 3 tint: `#1f1a0d`
- Metric line: `#7986cb`
- Alert threshold line: `#ef5350` dashed
- Axis labels: `#e8eaf6`
- Grid lines: `#2e2e4a`
- Callout boxes: `#23234a` fill, `#7986cb` border, `#e8eaf6` text

All layout and annotations unchanged. **920×400px**.