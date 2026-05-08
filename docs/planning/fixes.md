# Fixes — Existing System
*Created: 2026-05-08*

These are concrete issues in the current codebase that should be resolved before or alongside the new feature work. They are ordered by impact.

---

## Fix 1 — Postgres job store blocks the event loop

**Severity:** High  
**File:** `app/infra/jobs/postgres_job_store.py`

**Problem:**  
`PostgresJobStore` uses `psycopg2` with a `ThreadedConnectionPool`. Every `create`, `get`, `update_*` call is a synchronous blocking I/O operation called directly from async route handlers (via `JobService`, which is called from `AsyncInferenceService.submit()`). This blocks the uvicorn event loop thread under any meaningful load.

`asyncpg` is already installed (`asyncpg==0.31.0`) but unused.

**Fix:**  
Rewrite `PostgresJobStore` using `asyncpg`. The `JobStore` interface methods (`create`, `get`, `update_status`, `update_result`, `update_error`) should become `async def`. `JobService` and its callers in the service layer need corresponding `await` calls.

Alternatively, if keeping the sync interface is preferred (e.g. for the arq worker which runs outside the async loop), wrap all psycopg2 calls with `asyncio.get_event_loop().run_in_executor(None, ...)` in the async paths. The asyncpg rewrite is cleaner.

**Scope:** `postgres_job_store.py`, `job_service.py`, `async_inference_service.py`, `prediction_service.py`, route handlers that call job service methods.

---

## Fix 2 — Rate limiting guarantee silently degrades without Redis

**Severity:** Medium  
**File:** `app/security/rate_limit.py`

**Problem:**  
The in-process `RateLimiter` enforces limits per-process. When the server runs with multiple uvicorn workers (`--workers N`) or multiple replicas, each process has its own counter. A tenant can send N× the configured limit before any single process trips. There is no warning logged, no header indicating the mode, and no documentation at the endpoint level.

**Fix:**  
Two parts:
1. On startup, log a clear warning when `REDIS_URL` is not set: `"Rate limiting is per-process only. Set REDIS_URL for distributed enforcement."` This makes the degraded mode visible in logs.
2. Add an `X-RateLimit-Mode: local|distributed` response header so operators can see which mode is active from outside.

No behaviour change needed — just visibility.

**Scope:** `app/security/rate_limit.py`, `app/adapters/http/middleware/rate_limit.py`.

---

## Fix 3 — No graceful shutdown for in-flight async jobs (thread pool path)

**Severity:** Medium  
**File:** `app/adapters/http/app.py`

**Problem:**  
The lifespan shutdown calls `executor._executor.shutdown(wait=True, cancel_futures=False)` for CPU and GPU executors, which is correct for sync inference. However, async jobs submitted via `_fallback_submit` (the no-Redis path) run as fire-and-forget background tasks in the same thread pool. If the server receives SIGTERM mid-job, the executor drains but the job store is never updated — the job stays in `RUNNING` state permanently.

**Fix:**  
In `_fallback_submit` / `_fallback_submit_batch`, track submitted futures. On shutdown, after `executor.shutdown(wait=True)`, iterate any futures that raised `CancelledError` or were not completed and call `job_service.mark_failed(job_id, "ShutdownError", "server shutdown during execution")`.

A simpler alternative: add a `reap_stuck` call on startup (already implemented in `PostgresJobStore` and presumably `SQLiteJobStore`) that marks any `RUNNING` jobs older than a configurable threshold as `FAILED`. This handles crash recovery too.

**Scope:** `app/services/async_inference_service.py`, `app/adapters/http/app.py`.

---

## Fix 4 — Confusing dual directory convention for models

**Severity:** Low (developer experience)  
**Files:** `app/domain/registry/registry.py`, `app/domain/loading/local_loader.py`, README

**Problem:**  
Two separate directory conventions exist:
- `models/<name>/<version>/definition.py` — auto-discovery by the registry
- `model_artifacts/<name>/<version>/` — artifact root for `LocalModelLoader`

These are never explained together. A new contributor adding a model has to read both the registry code and the loader code to understand that `definition.py` is the entry point and `model_artifacts/` is where the actual weights go. The README's "Adding a Model" section mentions `model_artifacts/` only in the loader example, not in the main flow.

**Fix:**  
Update the README's "Adding a Model" section to explicitly show both directories together with a single example tree:

```
models/
└── sentiment/
    └── v1/
        └── definition.py       ← registry entry point

model_artifacts/
└── sentiment/
    └── v1/
        └── model.pkl           ← artifact loaded inside definition.py
```

No code change needed — documentation only.

**Scope:** `README.md`, optionally `docs/guides/adding-a-model.md`.

---

## Fix 5 — `asyncpg` and `psycopg2` both in core dependencies

**Severity:** Low (dependency hygiene)  
**File:** `pyproject.toml`

**Problem:**  
`asyncpg` is listed as a core dependency but is not used anywhere in the codebase. `psycopg2` is used. Having an unused dependency adds install weight and creates confusion about which Postgres driver is canonical.

**Fix:**  
Once Fix 1 is done (migrating to asyncpg), remove `psycopg2` from core deps and move it to an optional `[postgres-sync]` extra for the arq worker if needed. Until Fix 1 is done, move `asyncpg` to an optional extra or remove it.

**Scope:** `pyproject.toml`.

---

## Summary

| # | Issue | Severity | Effort |
|---|---|---|---|
| 1 | Postgres store blocks event loop | High | Medium — rewrite one file + propagate async |
| 2 | Rate limit degrades silently without Redis | Medium | Low — add log warning + response header |
| 3 | In-flight jobs not marked failed on shutdown | Medium | Low — startup reap or shutdown hook |
| 4 | Dual directory convention undocumented | Low | Trivial — README update |
| 5 | Unused asyncpg dependency | Low | Trivial — pyproject.toml cleanup |
