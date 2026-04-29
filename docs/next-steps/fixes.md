# Fixes & Improvements

Actionable fixes derived from the assessment, ordered by priority. Each entry has the problem, the exact fix, and the file(s) to change.

---

## P0 — Security (Fix Before Any Production Deployment)

### 1. Timing attack on API key comparison

**Problem:** `API_KEYS.get(api_key)` is a plain dict lookup. Python dict lookups short-circuit on the first differing character, making response time a function of how many characters of the key are correct. An attacker with enough requests can enumerate valid key prefixes.

**Fix:** Use `hmac.compare_digest` for constant-time comparison.

```python
# app/security/auth.py

import hmac

def authenticate(api_key: str) -> Identity | None:
    for key, identity in API_KEYS.items():
        if hmac.compare_digest(key, api_key):
            return identity
    return None
```

**Files:** `app/security/auth.py`

---

### 2. Hardcoded fallback keys active in production

**Problem:** When `API_KEYS` env var is not set, `dev-key` and `admin-key` are active. A production container missing this env var is fully open.

**Fix:** Add a startup guard that refuses to start when `ENV=production` and `API_KEYS` is unset.

```python
# app/adapters/http/app.py — inside create_app(), before middleware

import os
if os.environ.get("ENV") == "production" and not os.environ.get("API_KEYS", "").strip():
    raise RuntimeError(
        "API_KEYS must be set in production. "
        "Set ENV=development to use hardcoded dev keys."
    )
```

**Files:** `app/adapters/http/app.py`

---

## P1 — Correctness (Fix Before Sustained Load)

### 3. Silent Postgres → SQLite fallback

**Problem:** When `DATABASE_URL` is set but Postgres is unreachable, the code silently falls back to SQLite. A misconfigured `DATABASE_URL` in production will silently write jobs to a local SQLite file, losing data across restarts.

**Fix:** Log at `ERROR` level before falling back, or raise and refuse to start.

```python
# app/adapters/http/deps.py

import logging
_log = logging.getLogger(__name__)

@lru_cache
def get_job_store() -> JobStore:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        try:
            from app.infra.jobs.postgres_job_store import PostgresJobStore
            return PostgresJobStore(dsn=db_url)
        except Exception as exc:
            _log.error(
                "Failed to connect to Postgres (%s). "
                "Falling back to SQLite — THIS IS NOT SAFE IN PRODUCTION.",
                exc,
            )
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    return SQLiteJobStore()
```

**Files:** `app/adapters/http/deps.py`

---

### 4. Missing error logging in `_fallback_submit_batch`

**Problem:** `_fallback_submit` logs errors on failure; `_fallback_submit_batch` does not. A failed batch job silently disappears from logs.

**Fix:** Add the same error logging pattern.

```python
# app/services/async_inference_service.py — _fallback_submit_batch

def run():
    job_service.mark_running(job_id)
    try:
        result = registry.get(model, version).run_batch(payloads)
        job_service.mark_succeeded(job_id, result)
    except Exception as exc:
        _log.getLogger(__name__).error(
            "async batch job %s failed: %s", job_id, exc, exc_info=True
        )
        try:
            job_service.mark_failed(job_id, type(exc).__name__, str(exc))
        except Exception:
            pass
```

**Files:** `app/services/async_inference_service.py`

---

### 5. Stuck-job reaper

**Problem:** When a worker process is killed while a job is `RUNNING`, that job stays in `RUNNING` state forever. There is no mechanism to detect or recover these jobs.

**Fix:** Add an arq cron task (or a background thread for the no-Redis path) that marks jobs stuck in `RUNNING` for longer than `job_timeout` as `FAILED`.

```python
# app/infra/queue/worker.py

from arq import cron

async def reap_stuck_jobs(ctx: dict) -> None:
    """Mark RUNNING jobs older than 10 minutes as FAILED."""
    from datetime import datetime, timezone, timedelta
    job_service = ctx["job_service"]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    job_service.reap_stuck(before=cutoff)

class WorkerSettings:
    functions = [run_inference, run_batch_inference]
    cron_jobs = [cron(reap_stuck_jobs, minute={0, 10, 20, 30, 40, 50})]
    ...
```

Requires adding `reap_stuck(before: datetime)` to `JobStore` and both implementations.

**Files:** `app/infra/queue/worker.py`, `app/domain/jobs/job_store.py`, `app/infra/jobs/sqlite_job_store.py`, `app/infra/jobs/postgres_job_store.py`, `app/services/job_service.py`

---

## P2 — Testing (Fix Before Calling This Production-Ready)

### 6. Add coverage tooling

**Problem:** No coverage measurement. No way to know what percentage of the codebase is exercised.

**Fix:**

```toml
# pyproject.toml

[project.optional-dependencies]
dev = [
    "pytest==9.0.3",
    "httpx==0.28.1",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
pythonpath = ["."]
addopts = "--cov=app --cov-report=term-missing --cov-fail-under=80"
```

**Files:** `pyproject.toml`

---

### 7. Test for timing-safe key comparison

**Problem:** No regression test to catch if the `hmac.compare_digest` fix is reverted.

**Fix:** Add a test that verifies `authenticate` returns `None` for a key that shares a prefix with a valid key.

```python
# tests/test_phase1.py or a new tests/test_security.py

def test_authenticate_rejects_prefix_of_valid_key():
    from app.security.auth import authenticate
    # "dev-ke" is a prefix of "dev-key" — must not authenticate
    assert authenticate("dev-ke") is None

def test_authenticate_rejects_extension_of_valid_key():
    assert authenticate("dev-key-extra") is None
```

**Files:** `tests/test_security.py` (new)

---

### 8. Concurrent registry access test

**Problem:** The double-checked locking in `ModelRegistry.get()` is correct but untested under concurrent load.

**Fix:**

```python
# tests/test_phase4.py

def test_registry_concurrent_get_no_deadlock():
    import threading
    from app.domain.registry.registry import ModelRegistry
    registry = ModelRegistry()
    errors = []

    def worker():
        try:
            for _ in range(50):
                registry.get("echo", "v1")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
```

**Files:** `tests/test_phase4.py`

---

## P3 — Operational (Fix Before Scaling)

### 9. Fix `pyproject.toml` description

**Problem:** Description is still the placeholder text.

**Fix:**

```toml
description = "Production-grade, task-agnostic ML inference backend"
```

**Files:** `pyproject.toml`

---

### 10. Add queue depth metric

**Problem:** `executor_inflight` tracks in-flight jobs but there's no metric for jobs in `PENDING` state. Under async load, queue depth is the most important capacity signal.

**Fix:** Add a gauge that is updated when jobs are created and when they transition out of `PENDING`.

```python
# app/core/metrics.py

JOB_QUEUE_DEPTH = Gauge(
    "job_queue_depth",
    "Number of jobs currently in PENDING state",
    ["model", "version"],
)
```

Update in `JobService.create_job()` (inc) and `JobService.mark_running()` (dec).

**Files:** `app/core/metrics.py`, `app/services/job_service.py`

---

### 11. Dockerfile hardening

**Problem:** The Dockerfile is minimal — no multi-stage build, no non-root user, no `HEALTHCHECK` instruction.

**Fix:**

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd -m -u 1000 appuser
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY app/ app/
USER appuser
ENV PATH="/app/.venv/bin:$PATH"
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.adapters.http.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Files:** `Dockerfile`

---

## P4 — CLI Agent (Before Implementation)

### 12. Sandbox the pickle inspector

**Problem:** The CLI agent's `inspector.py` calls `pickle.load()` on a user-provided file. A malicious `.pkl` executes arbitrary Python at load time. This is a known, well-documented attack vector.

**Fix:** Run the inspector in a subprocess with a timeout. The subprocess has no network access and is killed if it exceeds the timeout.

```python
# app/cli/inspector.py

import subprocess, sys, json, tempfile, os

def inspect_artifact(path: str) -> dict:
    """Run artifact inspection in an isolated subprocess."""
    script = f"""
import pickle, json, sys
with open({path!r}, 'rb') as f:
    obj = pickle.load(f)
# ... extract metadata ...
print(json.dumps(metadata))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30,
        # No network: on Linux, could use unshare/seccomp
    )
    if result.returncode != 0:
        raise ValueError(f"Inspection failed: {result.stderr}")
    return json.loads(result.stdout)
```

Add a warning in the CLI output before loading any artifact:

```
⚠ Warning: loading a pickle file executes arbitrary Python code.
  Only load artifacts from sources you trust.
  Continue? (Y/n)
```

**Files:** `app/cli/inspector.py` (new)

---

### 13. Document LLM API key requirements

**Problem:** The agent design doc doesn't specify how the LLM API key is provided or what error the user sees if it's missing.

**Fix:** Add to the agent design doc and implement a pre-flight check in `agent.py`:

```python
# app/cli/agent.py

def _check_provider_key(provider: str) -> None:
    key_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
    }
    if provider in key_map and not os.environ.get(key_map[provider]):
        raise SystemExit(
            f"Error: {key_map[provider]} environment variable is not set.\n"
            f"Set it with: export {key_map[provider]}=<your-key>"
        )
```

**Files:** `app/cli/agent.py` (new), `docs/next-steps/agent.md`

---

### 14. Non-TTY / `--non-interactive` support in CLI

**Problem:** `questionary` prompts hang in CI, Docker, or piped input. The CLI has no way to be driven non-interactively.

**Fix:** Add CLI flags for all prompts so the tool can be scripted:

```bash
inference-engine init ./model.pkl \
  --name sentiment \
  --version v1 \
  --device cpu \
  --routing static \
  --sample-input "this movie was great"
```

When all flags are provided, skip the interactive prompts entirely.

**Files:** `app/cli/__main__.py` (new), `app/cli/init.py` (new)

---

## Summary Table

| # | Priority | Area | Effort | Impact |
|---|---|---|---|---|
| 1 | P0 | Security | 5 min | High — prevents timing attack |
| 2 | P0 | Security | 10 min | High — prevents open prod keys |
| 3 | P1 | Correctness | 5 min | High — prevents silent data loss |
| 4 | P1 | Correctness | 5 min | Low — log consistency |
| 5 | P1 | Correctness | 2h | High — prevents stuck jobs |
| 6 | P2 | Testing | 15 min | Medium — establishes coverage baseline |
| 7 | P2 | Testing | 15 min | Medium — regression guard |
| 8 | P2 | Testing | 30 min | Medium — concurrency correctness |
| 9 | P3 | Polish | 1 min | Low |
| 10 | P3 | Observability | 1h | Medium — capacity planning signal |
| 11 | P3 | Operations | 30 min | Medium — production container hygiene |
| 12 | P4 | CLI Agent | 2h | High — prevents RCE via malicious pkl |
| 13 | P4 | CLI Agent | 30 min | Medium — clear user error messages |
| 14 | P4 | CLI Agent | 1h | Medium — CI/scripting support |
