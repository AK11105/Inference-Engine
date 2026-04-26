"""
Phase 1 test suite.
"""

import threading
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"X-API-Key": "dev-key"}


# ---------------------------------------------------------------------------
# Shared fixture: app wired to in-memory SQLite + real registry
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_client():
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    from app.services.job_service import JobService
    from app.domain.registry.registry import ModelRegistry
    from app.adapters.http import deps
    from app.adapters.http.app import create_app

    real_registry = ModelRegistry()
    job_service = JobService(SQLiteJobStore(db_path=":memory:"))

    orig_get_registry = deps.get_registry
    orig_get_job_service = deps.get_job_service

    with patch.object(deps, "get_registry", return_value=real_registry):
        with patch.object(deps, "get_job_service", return_value=job_service):
            app = create_app()
            app.dependency_overrides[orig_get_registry] = lambda: real_registry
            app.dependency_overrides[orig_get_job_service] = lambda: job_service
            with TestClient(app) as client:
                yield client, real_registry


@pytest.fixture()
def unready_app_client():
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    from app.services.job_service import JobService
    from app.adapters.http import deps
    from app.adapters.http.app import create_app
    from app.domain.registry.registry import ModelRegistry

    mock_registry = MagicMock(spec=ModelRegistry)
    mock_registry.is_ready.return_value = False
    mock_registry.warm_up.return_value = None

    job_service = JobService(SQLiteJobStore(db_path=":memory:"))

    orig_get_registry = deps.get_registry
    orig_get_job_service = deps.get_job_service

    with patch.object(deps, "get_registry", return_value=mock_registry):
        with patch.object(deps, "get_job_service", return_value=job_service):
            app = create_app()
            app.dependency_overrides[orig_get_registry] = lambda: mock_registry
            app.dependency_overrides[orig_get_job_service] = lambda: job_service
            with TestClient(app) as client:
                yield client, mock_registry


# ---------------------------------------------------------------------------
# 1. Thread-safe ModelRegistry
# ---------------------------------------------------------------------------

class TestModelRegistry:
    def test_get_returns_pipeline(self):
        from app.domain.registry.registry import ModelRegistry
        assert ModelRegistry().get("echo", "v1") is not None

    def test_get_same_object_on_second_call(self):
        from app.domain.registry.registry import ModelRegistry
        r = ModelRegistry()
        assert r.get("echo", "v1") is r.get("echo", "v1")

    def test_get_raises_for_unknown_model(self):
        from app.domain.registry.registry import ModelRegistry, ModelNotFoundError
        with pytest.raises(ModelNotFoundError):
            ModelRegistry().get("nonexistent", "v99")

    def test_warm_up_sets_is_ready(self):
        from app.domain.registry.registry import ModelRegistry
        r = ModelRegistry()
        assert not r.is_ready()
        r.warm_up()
        assert r.is_ready()

    def test_list_models_contains_both_versions(self):
        from app.domain.registry.registry import ModelRegistry
        models = ModelRegistry().list_models()
        assert ("echo", "v1") in models
        assert ("echo", "v2") in models

    def test_different_versions_are_distinct_objects(self):
        from app.domain.registry.registry import ModelRegistry
        r = ModelRegistry()
        assert r.get("echo", "v1") is not r.get("echo", "v2")

    def test_no_duplicate_builds_under_concurrency(self):
        from app.domain.registry.registry import ModelRegistry
        import app.domain.definitions.echo_v1 as echo_v1_mod

        build_count = {"n": 0}
        original_build = echo_v1_mod.build_pipeline

        def slow_build():
            build_count["n"] += 1
            time.sleep(0.05)
            return original_build()

        r = ModelRegistry()
        r._definitions[("echo", "v1")] = slow_build

        results, errors = [], []

        def worker():
            try:
                results.append(r.get("echo", "v1"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert build_count["n"] == 1
        assert len(set(id(obj) for obj in results)) == 1


# ---------------------------------------------------------------------------
# 2. ExecutionPolicy — bare except fix
# ---------------------------------------------------------------------------

class TestExecutionPolicy:
    def _make(self, policy_map=None, default="cpu", extra=None):
        from app.execution.execution_policy import ExecutionPolicy
        executors = {"cpu": MagicMock(), **(extra or {})}
        return ExecutionPolicy(executors=executors, policy=policy_map or {}, default=default), executors

    def test_resolve_returns_default_executor(self):
        policy, executors = self._make()
        assert policy.resolve("echo", "v1") is executors["cpu"]

    def test_resolve_returns_mapped_executor(self):
        gpu = MagicMock()
        policy, _ = self._make(policy_map={"echo:v1": "gpu"}, extra={"gpu": gpu})
        assert policy.resolve("echo", "v1") is gpu

    def test_unknown_executor_raises_runtime_error(self):
        from app.execution.execution_policy import ExecutionPolicy
        policy = ExecutionPolicy(
            executors={"cpu": MagicMock()},
            policy={"echo:v1": "triton"},
            default="cpu",
        )
        with pytest.raises(RuntimeError, match="Unknown executor"):
            policy.resolve("echo", "v1")

    def test_keyboard_interrupt_propagates(self):
        from app.execution.execution_policy import ExecutionPolicy

        class Boom(dict):
            def __getitem__(self, key):
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            ExecutionPolicy(executors=Boom(), policy={}, default="cpu").resolve("echo", "v1")

    def test_system_exit_propagates(self):
        from app.execution.execution_policy import ExecutionPolicy

        class Boom(dict):
            def __getitem__(self, key):
                raise SystemExit(1)

        with pytest.raises(SystemExit):
            ExecutionPolicy(executors=Boom(), policy={}, default="cpu").resolve("echo", "v1")


# ---------------------------------------------------------------------------
# 3. Warm-up at startup
# ---------------------------------------------------------------------------

class TestWarmUp:
    def test_warm_up_called_during_lifespan(self, unready_app_client):
        _, mock_registry = unready_app_client
        mock_registry.warm_up.assert_called_once()

    def test_registry_is_ready_after_startup(self, app_client):
        _, real_registry = app_client
        assert real_registry.is_ready()


# ---------------------------------------------------------------------------
# 4. /ready endpoint
# ---------------------------------------------------------------------------

class TestReadyEndpoint:
    def test_returns_200_when_models_loaded(self, app_client):
        client, _ = app_client
        resp = client.get("/ready", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_returns_503_when_models_not_loaded(self, unready_app_client):
        client, _ = unready_app_client
        resp = client.get("/ready", headers=AUTH_HEADERS)
        assert resp.status_code == 503
        assert resp.json()["status"] == "loading"

    def test_transitions_503_to_200(self, unready_app_client):
        client, mock_registry = unready_app_client
        assert client.get("/ready", headers=AUTH_HEADERS).status_code == 503
        mock_registry.is_ready.return_value = True
        assert client.get("/ready", headers=AUTH_HEADERS).status_code == 200


# ---------------------------------------------------------------------------
# 5. HTTP integration
# ---------------------------------------------------------------------------

class TestHTTPIntegration:
    def test_health_no_auth(self, app_client):
        client, _ = app_client
        assert client.get("/health").status_code == 200

    def test_predict_missing_key_401(self, app_client):
        client, _ = app_client
        assert client.post("/predict", json={"model": "echo", "version": "v1", "data": "hi"}).status_code == 401

    def test_predict_bad_key_401(self, app_client):
        client, _ = app_client
        resp = client.post("/predict", json={"model": "echo", "version": "v1", "data": "hi"}, headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_predict_echo_v1(self, app_client):
        client, _ = app_client
        resp = client.post("/predict", json={"model": "echo", "version": "v1", "data": "hello"}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["result"] == "hello"

    def test_predict_echo_v2(self, app_client):
        client, _ = app_client
        resp = client.post("/predict", json={"model": "echo", "version": "v2", "data": 42}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["result"] == 42

    def test_predict_unknown_model_400(self, app_client):
        client, _ = app_client
        resp = client.post("/predict", json={"model": "ghost", "version": "v1", "data": "x"}, headers=AUTH_HEADERS)
        assert resp.status_code == 400

    def test_predict_batch(self, app_client):
        client, _ = app_client
        resp = client.post("/predict/batch", json={"model": "echo", "version": "v1", "items": ["a", "b", "c"]}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["results"] == ["a", "b", "c"]

    def test_models_endpoint(self, app_client):
        client, _ = app_client
        assert client.get("/models", headers=AUTH_HEADERS).status_code == 200

    def test_ready_after_startup(self, app_client):
        client, _ = app_client
        assert client.get("/ready", headers=AUTH_HEADERS).status_code == 200

    def test_async_predict_submit_and_poll(self, app_client):
        client, _ = app_client
        resp = client.post("/predict/async", json={"model": "echo", "version": "v1", "data": "async-test"}, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]

        deadline = time.time() + 10
        while time.time() < deadline:
            poll = client.get(f"/predict/async/{job_id}", headers=AUTH_HEADERS)
            assert poll.status_code == 200
            if poll.json()["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)

        assert poll.json()["status"] == "succeeded"
        assert poll.json()["result"] == "async-test"

    def test_async_unknown_job_404(self, app_client):
        client, _ = app_client
        assert client.get(f"/predict/async/{uuid4()}", headers=AUTH_HEADERS).status_code == 404

    def test_request_id_echoed_in_response(self, app_client):
        client, _ = app_client
        resp = client.post(
            "/predict", json={"model": "echo", "version": "v1", "data": "x"},
            headers={**AUTH_HEADERS, "X-Request-ID": "my-req-123"},
        )
        assert resp.headers.get("X-Request-ID") == "my-req-123"


# ---------------------------------------------------------------------------
# 6. RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_within_limit(self):
        from app.security.rate_limit import RateLimiter
        rl = RateLimiter(rate=5, per_seconds=1)
        assert all(rl.allow("k") for _ in range(5))

    def test_blocks_over_limit(self):
        from app.security.rate_limit import RateLimiter
        rl = RateLimiter(rate=3, per_seconds=1)
        for _ in range(3):
            rl.allow("k")
        assert rl.allow("k") is False

    def test_different_keys_are_independent(self):
        from app.security.rate_limit import RateLimiter
        rl = RateLimiter(rate=1, per_seconds=1)
        assert rl.allow("a") is True
        assert rl.allow("b") is True

    def test_window_resets_after_expiry(self):
        from app.security.rate_limit import RateLimiter
        rl = RateLimiter(rate=1, per_seconds=1)
        rl.allow("k")
        assert rl.allow("k") is False
        rl._events["k"][0] = time.time() - 2
        assert rl.allow("k") is True


# ---------------------------------------------------------------------------
# 7. Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_valid_key_returns_identity(self):
        from app.security.auth import authenticate
        identity = authenticate("dev-key")
        assert identity is not None
        assert identity.tenant_id == "tenant_dev"

    def test_invalid_key_returns_none(self):
        from app.security.auth import authenticate
        assert authenticate("not-real") is None

    def test_admin_key_has_admin_scope(self):
        from app.security.auth import authenticate
        assert "admin" in authenticate("admin-key").scopes

    def test_dev_key_lacks_admin_scope(self):
        from app.security.auth import authenticate
        assert "admin" not in authenticate("dev-key").scopes
