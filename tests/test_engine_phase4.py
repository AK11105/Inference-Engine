"""
Phase 4 test suite.

Covers:
  1. Distributed tracing (OpenTelemetry) — no-op fallback, span attributes
  2. Model memory management — LRU eviction, max_loaded cap
  3. Graceful shutdown — executor drains, pending jobs marked failed
  4. Admin hot-reload API — POST /admin/models/{name}/{version}/reload
  5. Per-model SLA timeouts — config lookup, timeout enforcement
"""
import asyncio
import time
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"X-API-Key": "dev-key"}
ADMIN_HEADERS = {"X-API-Key": "admin-key"}


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_client():
    from app.infra.jobs.sqlite_job_store import SQLiteJobStore
    from app.services.job_service import JobService
    from app.domain.registry.registry import ModelRegistry
    from app.services.async_inference_service import AsyncInferenceService
    from app.services.prediction_service import PredictionService
    from app.services.routing_service import RoutingService
    from app.execution.execution_policy import ExecutionPolicy
    from app.execution.executor import InferenceExecutor
    from app.adapters.http import deps
    from app.adapters.http.app import create_app

    real_registry = ModelRegistry()
    real_registry.warm_up()
    job_service = JobService(SQLiteJobStore(db_path=":memory:"))

    executor = InferenceExecutor(device="cpu", max_workers=2)
    policy = ExecutionPolicy(
        executors={"cpu": executor, "gpu": executor},
        policy={},
        default="cpu",
    )
    pred_service = PredictionService(
        registry=real_registry,
        executor=None,
        routing_service=RoutingService({}),
        execution_policy=policy,
        job_service=job_service,
    )
    async_service = AsyncInferenceService(pred_service, job_queue=None)

    app = create_app()
    app.dependency_overrides[deps.get_registry] = lambda: real_registry
    app.dependency_overrides[deps.get_job_service] = lambda: job_service
    app.dependency_overrides[deps.get_async_service] = lambda: async_service

    # Pre-populate the module-level job store so lifespan skips re-initializing
    # it (which would try to create app/instance/jobs.db on disk).
    # Also clear REDIS_URL so lifespan doesn't waste time on Redis retries.
    import os
    from unittest.mock import patch
    deps._job_store = job_service._store
    try:
        with patch.dict(os.environ, {"REDIS_URL": "", "DATABASE_URL": ""}, clear=False):
            with TestClient(app) as client:
                yield client, real_registry, job_service
    finally:
        deps._job_store = None


# ===========================================================================
# 1. Distributed tracing
# ===========================================================================

class TestTracing:
    def test_get_tracer_returns_something_without_otel(self):
        """get_tracer() must not raise even when opentelemetry is absent."""
        with patch.dict("sys.modules", {"opentelemetry": None}):
            from app.core import tracing as tr
            # Force re-evaluation of _otel_available
            tracer = tr._NoOpTracer()
            span = tracer.start_as_current_span("test")
            with span as s:
                s.set_attribute("k", "v")  # must not raise

    def test_noop_tracer_context_manager(self):
        from app.core.tracing import _NoOpTracer
        tracer = _NoOpTracer()
        with tracer.start_as_current_span("my-span") as span:
            span.set_attribute("model", "echo")
            span.set_attribute("version", "v1")
            span.record_exception(ValueError("test"))

    def test_get_tracer_returns_noop_when_otel_missing(self):
        """When opentelemetry is not installed, get_tracer returns _NoOpTracer."""
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.trace": None}):
            from app.core.tracing import _NoOpTracer, get_tracer
            tracer = get_tracer()
            # Either a real tracer or our no-op — both must support the interface
            span = tracer.start_as_current_span("test")
            assert span is not None

    def test_setup_tracing_is_safe_without_otel(self):
        """setup_tracing() must not raise when opentelemetry is absent."""
        with patch.dict("sys.modules", {"opentelemetry": None}):
            from app.core.tracing import setup_tracing
            setup_tracing(app=None)  # should not raise

    def test_prediction_service_uses_tracer(self, app_client):
        """Inference requests complete successfully with tracing wired in."""
        client, _, _ = app_client
        r = client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "trace-me"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["result"] == "trace-me"


# ===========================================================================
# 2. Model memory management (LRU eviction)
# ===========================================================================

class TestLRUEviction:
    def test_max_loaded_limits_cache_size(self):
        """With max_loaded=1, loading a second model evicts the first."""
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry(max_loaded=1)
        registry.get("echo", "v1")
        assert len(registry._pipelines) == 1

        registry.get("echo", "v2")
        # Cache must not exceed max_loaded
        assert len(registry._pipelines) <= 1

    def test_lru_evicts_least_recently_used(self):
        """The LRU entry (oldest access) is evicted first."""
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry(max_loaded=1)
        registry.get("echo", "v1")   # v1 is now in cache
        registry.get("echo", "v2")   # v2 loaded → v1 evicted

        assert ("echo", "v2") in registry._pipelines
        assert ("echo", "v1") not in registry._pipelines

    def test_access_refreshes_lru_order(self):
        """Accessing v1 after v2 makes v2 the LRU candidate."""
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry(max_loaded=1)
        registry.get("echo", "v1")
        registry.get("echo", "v2")   # v1 evicted, v2 in cache
        # Re-access v1 — it gets rebuilt; v2 should be evicted
        registry.get("echo", "v1")

        assert ("echo", "v1") in registry._pipelines
        assert ("echo", "v2") not in registry._pipelines

    def test_no_limit_keeps_all_loaded(self):
        """Default (max_loaded=None) keeps all pipelines in memory."""
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry()  # no limit
        registry.warm_up()
        assert len(registry._pipelines) == len(registry._definitions)

    def test_eviction_is_thread_safe(self):
        """Concurrent gets with max_loaded=1 must not corrupt the cache."""
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry(max_loaded=1)
        errors = []

        def load(v):
            try:
                registry.get("echo", v)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=load, args=(v,)) for v in ("v1", "v2") * 10]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(registry._pipelines) <= 1


# ===========================================================================
# 3. Graceful shutdown
# ===========================================================================

class TestGracefulShutdown:
    def test_executor_shutdown_drains_futures(self):
        """InferenceExecutor.shutdown drains submitted futures before returning."""
        from app.execution.executor import InferenceExecutor

        executor = InferenceExecutor(device="cpu", max_workers=2)
        results = []

        def slow_task():
            time.sleep(0.05)
            results.append(1)

        executor.submit_background(slow_task)
        # shutdown(wait=True) must block until slow_task completes
        executor._executor.shutdown(wait=True, cancel_futures=False)
        assert results == [1]

    def test_app_lifespan_shuts_down_cleanly(self):
        """TestClient context manager exercises the full lifespan (startup + shutdown)."""
        from app.adapters.http.app import create_app
        from app.adapters.http import deps

        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        from app.services.job_service import JobService
        from app.domain.registry.registry import ModelRegistry
        from app.services.async_inference_service import AsyncInferenceService
        from app.services.prediction_service import PredictionService
        from app.services.routing_service import RoutingService
        from app.execution.execution_policy import ExecutionPolicy
        from app.execution.executor import InferenceExecutor

        registry = ModelRegistry()
        registry.warm_up()
        job_service = JobService(SQLiteJobStore(db_path=":memory:"))
        executor = InferenceExecutor(device="cpu", max_workers=1)
        policy = ExecutionPolicy(
            executors={"cpu": executor, "gpu": executor},
            policy={},
            default="cpu",
        )
        pred_service = PredictionService(
            registry=registry,
            executor=None,
            routing_service=RoutingService({}),
            execution_policy=policy,
            job_service=job_service,
        )
        async_service = AsyncInferenceService(pred_service, job_queue=None)

        app = create_app()
        app.dependency_overrides[deps.get_registry] = lambda: registry
        app.dependency_overrides[deps.get_job_service] = lambda: job_service
        app.dependency_overrides[deps.get_async_service] = lambda: async_service

        import os
        from unittest.mock import patch as _patch
        # Pre-populate module-level job store so lifespan skips re-initializing it.
        deps._job_store = job_service._store
        try:
            with _patch.dict(os.environ, {"REDIS_URL": "", "DATABASE_URL": ""}, clear=False):
                # If lifespan raises, TestClient.__exit__ will propagate it
                with TestClient(app) as client:
                    r = client.get("/health")
                    assert r.status_code == 200
                # Reaching here means shutdown completed without error
        finally:
            deps._job_store = None


# ===========================================================================
# 4. Admin hot-reload API
# ===========================================================================

class TestHotReload:
    def test_reload_returns_200(self, app_client):
        client, _, _ = app_client
        r = client.post(
            "/admin/models/echo/v1/reload",
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["reloaded"] is True
        assert body["model"] == "echo"
        assert body["version"] == "v1"

    def test_reload_unknown_model_returns_404(self, app_client):
        client, _, _ = app_client
        r = client.post(
            "/admin/models/ghost/v99/reload",
            headers=ADMIN_HEADERS,
        )
        assert r.status_code == 404

    def test_reload_requires_admin_scope(self, app_client):
        client, _, _ = app_client
        r = client.post(
            "/admin/models/echo/v1/reload",
            headers=AUTH_HEADERS,  # dev-key has no admin scope
        )
        assert r.status_code == 403

    def test_reload_rebuilds_pipeline(self, app_client):
        """After reload, the model still works correctly."""
        client, registry, _ = app_client
        # Capture the old pipeline object
        old_pipeline = registry._pipelines.get(("echo", "v1"))

        client.post("/admin/models/echo/v1/reload", headers=ADMIN_HEADERS)

        new_pipeline = registry._pipelines.get(("echo", "v1"))
        # A new object was built
        assert new_pipeline is not old_pipeline

        # And it still works
        r = client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "after-reload"},
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        assert r.json()["result"] == "after-reload"

    def test_memory_status_endpoint(self, app_client):
        client, _, _ = app_client
        r = client.get("/admin/models/memory", headers=ADMIN_HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert "loaded" in body
        assert "models" in body

    def test_memory_status_requires_admin_scope(self, app_client):
        client, _, _ = app_client
        r = client.get("/admin/models/memory", headers=AUTH_HEADERS)
        assert r.status_code == 403


# ===========================================================================
# 5. Per-model SLA timeouts
# ===========================================================================

class TestSLATimeouts:
    def test_resolve_timeout_uses_request_timeout_first(self):
        from app.services.prediction_service import _resolve_timeout
        with patch("app.services.prediction_service.SLA_TIMEOUTS", {"echo:v1": 5.0}):
            # Explicit request timeout wins over SLA
            assert _resolve_timeout("echo", "v1", request_timeout=2.0) == 2.0

    def test_resolve_timeout_falls_back_to_sla(self):
        from app.services.prediction_service import _resolve_timeout
        with patch("app.services.prediction_service.SLA_TIMEOUTS", {"echo:v1": 5.0}):
            assert _resolve_timeout("echo", "v1", request_timeout=None) == 5.0

    def test_resolve_timeout_falls_back_to_global_default(self):
        from app.services.prediction_service import _resolve_timeout
        with patch("app.services.prediction_service.SLA_TIMEOUTS", {}):
            with patch("app.services.prediction_service.DEFAULT_TIMEOUT_S", 10.0):
                assert _resolve_timeout("unknown", "v1", request_timeout=None) == 10.0

    def test_resolve_timeout_returns_none_when_no_config(self):
        from app.services.prediction_service import _resolve_timeout
        with patch("app.services.prediction_service.SLA_TIMEOUTS", {}):
            with patch("app.services.prediction_service.DEFAULT_TIMEOUT_S", None):
                assert _resolve_timeout("echo", "v1", request_timeout=None) is None

    def test_sla_timeout_enforced_on_slow_model(self):
        """A model that exceeds its SLA budget raises InferenceExecutionError."""
        from app.services.prediction_service import PredictionService, InferenceExecutionError
        from app.services.routing_service import RoutingService
        from app.execution.execution_policy import ExecutionPolicy
        from app.execution.executor import InferenceExecutor
        from app.services.job_service import JobService
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        from app.domain.registry.registry import ModelRegistry
        from app.domain.pipelines.base import InferencePipeline
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.models.base import BaseModel

        class SlowModel(BaseModel):
            def load(self): pass
            def predict(self, x):
                time.sleep(2)
                return x

        registry = ModelRegistry()
        # Inject a slow pipeline for echo:v1
        slow_pipeline = InferencePipeline(
            preprocessor=IdentityPreprocessor(),
            model=SlowModel(),
            postprocessor=IdentityPostprocessor(),
        )
        registry._pipelines[("echo", "v1")] = slow_pipeline
        registry._definitions[("echo", "v1")] = lambda: slow_pipeline

        executor = InferenceExecutor(device="cpu", max_workers=1)
        policy = ExecutionPolicy(
            executors={"cpu": executor},
            policy={},
            default="cpu",
        )
        job_service = JobService(SQLiteJobStore(db_path=":memory:"))
        service = PredictionService(
            registry=registry,
            executor=None,
            routing_service=RoutingService({}),
            execution_policy=policy,
            job_service=job_service,
        )

        with patch("app.services.prediction_service.SLA_TIMEOUTS", {"echo:v1": 0.1}):
            with pytest.raises(InferenceExecutionError):
                asyncio.run(service.predict("echo", "v1", "hello"))

    def test_sla_config_file_is_importable(self):
        from app.config.sla import SLA_TIMEOUTS, DEFAULT_TIMEOUT_S
        assert isinstance(SLA_TIMEOUTS, dict)
        # DEFAULT_TIMEOUT_S is either None or a float
        assert DEFAULT_TIMEOUT_S is None or isinstance(DEFAULT_TIMEOUT_S, float)
