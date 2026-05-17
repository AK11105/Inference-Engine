"""
Security regression tests.

Covers:
  1. Timing-safe API key comparison (hmac.compare_digest)
  2. Stuck-job reaper (reap_stuck)
  3. Concurrent registry access (no deadlock)
  4. Production guard (ENV=production without API_KEYS)
"""
import asyncio
import threading
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. Timing-safe API key comparison
# ---------------------------------------------------------------------------

class TestTimingSafeAuth:
    def test_authenticate_valid_key(self):
        from app.security.auth import authenticate
        identity = authenticate("dev-key")
        assert identity is not None
        assert identity.tenant_id == "tenant_dev"

    def test_authenticate_rejects_prefix_of_valid_key(self):
        from app.security.auth import authenticate
        assert authenticate("dev-ke") is None

    def test_authenticate_rejects_extension_of_valid_key(self):
        from app.security.auth import authenticate
        assert authenticate("dev-key-extra") is None

    def test_authenticate_rejects_unknown_key(self):
        from app.security.auth import authenticate
        assert authenticate("totally-unknown") is None

    def test_authenticate_rejects_empty_string(self):
        from app.security.auth import authenticate
        assert authenticate("") is None

    def test_authenticate_uses_hmac_compare_digest(self):
        """Verify the implementation uses hmac.compare_digest, not plain dict lookup."""
        import inspect
        import app.security.auth as auth_module
        source = inspect.getsource(auth_module.authenticate)
        assert "compare_digest" in source, (
            "authenticate() must use hmac.compare_digest for constant-time comparison"
        )


# ---------------------------------------------------------------------------
# 2. Stuck-job reaper
# ---------------------------------------------------------------------------

class TestReapStuck:
    def _make_store(self):
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        return SQLiteJobStore(db_path=":memory:")

    def _make_service(self, store):
        from app.services.job_service import JobService
        return JobService(store)

    def test_reap_stuck_marks_old_running_jobs_failed(self):
        store = self._make_store()
        svc = self._make_service(store)

        job_id = asyncio.run(svc.create_job("echo", "v1", "payload"))
        asyncio.run(svc.mark_running(job_id))

        cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
        count = asyncio.run(svc.reap_stuck(before=cutoff))
        assert count == 1

        job = asyncio.run(svc.get_job(job_id))
        from app.domain.jobs.job_state import JobStatus
        assert job.status == JobStatus.FAILED
        assert "reaped" in (job.error_message or "")

    def test_reap_stuck_does_not_affect_recent_running_jobs(self):
        store = self._make_store()
        svc = self._make_service(store)

        job_id = asyncio.run(svc.create_job("echo", "v1", "payload"))
        asyncio.run(svc.mark_running(job_id))

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        count = asyncio.run(svc.reap_stuck(before=cutoff))
        assert count == 0

        job = asyncio.run(svc.get_job(job_id))
        from app.domain.jobs.job_state import JobStatus
        assert job.status == JobStatus.RUNNING

    def test_reap_stuck_does_not_affect_succeeded_jobs(self):
        store = self._make_store()
        svc = self._make_service(store)

        job_id = asyncio.run(svc.create_job("echo", "v1", "payload"))
        asyncio.run(svc.mark_running(job_id))
        asyncio.run(svc.mark_succeeded(job_id, "result"))

        cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
        count = asyncio.run(svc.reap_stuck(before=cutoff))
        assert count == 0

        job = asyncio.run(svc.get_job(job_id))
        from app.domain.jobs.job_state import JobStatus
        assert job.status == JobStatus.SUCCEEDED


# ---------------------------------------------------------------------------
# 3. Concurrent registry access — no deadlock
# ---------------------------------------------------------------------------

class TestConcurrentRegistry:
    def test_registry_concurrent_get_no_deadlock(self):
        from app.domain.registry.registry import ModelRegistry
        registry = ModelRegistry()
        registry.warm_up()
        errors = []

        def worker():
            try:
                for _ in range(50):
                    registry.get("echo", "v1")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Concurrent registry access raised: {errors}"


# ---------------------------------------------------------------------------
# 4. Production guard
# ---------------------------------------------------------------------------

class TestProductionGuard:
    def test_create_app_raises_in_production_without_api_keys(self):
        import os
        env = {"ENV": "production", "API_KEYS": ""}
        with patch.dict(os.environ, env, clear=False):
            import app.adapters.http.app as app_module
            with pytest.raises(RuntimeError, match="API_KEYS must be set in production"):
                app_module.create_app()

    def test_create_app_succeeds_in_development_without_api_keys(self):
        import os
        env = {"ENV": "development", "API_KEYS": ""}
        with patch.dict(os.environ, env, clear=False):
            import app.adapters.http.app as app_module
            app_module.create_app()

