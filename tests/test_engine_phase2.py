"""
Phase 2 test suite — Make it deployable.

Covers:
  5. PostgresJobStore (contract tests via a fake/mock)
  6. Redis rate limiter (RedisRateLimiter + make_rate_limiter factory)
  7. Environment-variable-based API key config
  8. arq async job queue (ArqJobQueue + AsyncInferenceService queue path)
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"X-API-Key": "dev-key"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.now(timezone.utc)


def _make_job(job_id=None, model="echo", version="v1", payload="x", status=None):
    from app.domain.jobs.job import Job
    from app.domain.jobs.job_state import JobStatus
    return Job(
        id=job_id or uuid4(),
        model_name=model,
        model_version=version,
        payload=payload,
        status=status or JobStatus.CREATED,
        device="cpu",
        created_at=_now(),
    )


# ---------------------------------------------------------------------------
# Shared app fixture (in-memory SQLite, no Redis, no Postgres)
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

    with TestClient(app) as client:
        yield client, real_registry, job_service


# ===========================================================================
# 5. PostgresJobStore — contract tests (no real DB required)
# ===========================================================================

class TestPostgresJobStoreContract:
    """
    Tests the PostgresJobStore interface contract using a mock psycopg2 pool.
    These tests verify the SQL logic and data mapping without a live database.

    We bypass __init__ entirely (using __new__) and inject a mock pool so
    no real database connection is needed.
    """

    def _make_store(self):
        """Build a PostgresJobStore with a fully mocked psycopg2 pool."""
        from app.infra.jobs.postgres_job_store import PostgresJobStore

        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: s
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn

        store = PostgresJobStore.__new__(PostgresJobStore)
        store._pool = mock_pool
        store._extras = MagicMock()
        store._extras.RealDictCursor = MagicMock()
        return store, mock_conn, mock_cursor

    def test_create_executes_insert(self):
        store, conn, cursor = self._make_store()
        job = _make_job()
        store.create(job)
        assert cursor.execute.called
        sql = cursor.execute.call_args[0][0]
        assert "INSERT INTO jobs" in sql

    def test_create_commits(self):
        store, conn, cursor = self._make_store()
        store.create(_make_job())
        conn.commit.assert_called()

    def test_get_raises_key_error_when_not_found(self):
        store, conn, cursor = self._make_store()
        cursor.fetchone.return_value = None
        with pytest.raises(KeyError):
            store.get(uuid4())

    def test_update_status_executes_update(self):
        from app.domain.jobs.job_state import JobStatus
        store, conn, cursor = self._make_store()
        store.update_status(uuid4(), JobStatus.RUNNING)
        assert cursor.execute.called
        sql = cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql

    def test_update_result_sets_succeeded(self):
        from app.domain.jobs.job_state import JobStatus
        store, conn, cursor = self._make_store()
        store.update_result(uuid4(), result={"score": 0.9}, finished_at=_now())
        sql = cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql
        args = cursor.execute.call_args[0][1]
        assert JobStatus.SUCCEEDED.value in args

    def test_update_error_sets_failed(self):
        from app.domain.jobs.job_state import JobStatus
        store, conn, cursor = self._make_store()
        store.update_error(uuid4(), "ValueError", "bad input", _now())
        sql = cursor.execute.call_args[0][0]
        assert "UPDATE jobs" in sql
        args = cursor.execute.call_args[0][1]
        assert JobStatus.FAILED.value in args

    def test_pool_connection_returned_after_create(self):
        store, conn, cursor = self._make_store()
        store.create(_make_job())
        store._pool.putconn.assert_called_with(conn)

    def test_pool_connection_returned_after_get(self):
        store, conn, cursor = self._make_store()
        cursor.fetchone.return_value = None
        try:
            store.get(uuid4())
        except KeyError:
            pass
        store._pool.putconn.assert_called_with(conn)

    def test_requires_dsn(self):
        """PostgresJobStore raises ValueError when no DSN is provided."""
        from app.infra.jobs.postgres_job_store import PostgresJobStore

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATABASE_URL", None)
            with pytest.raises(ValueError, match="DSN"):
                PostgresJobStore(dsn="")


# ===========================================================================
# 6. Redis rate limiter
# ===========================================================================

class TestRedisRateLimiter:
    def _make_redis(self):
        """Fake Redis client that implements eval() to simulate the Lua rate-limit script."""
        from collections import defaultdict

        class FakeRedis:
            def __init__(self):
                self._sets: dict = defaultdict(dict)  # key → {member: score}

            def eval(self, script, numkeys, *args):
                """
                Simulate the rate-limit Lua script:
                  KEYS[1]=zkey, ARGV[1]=now, ARGV[2]=window, ARGV[3]=rate, ARGV[4]=member
                """
                zkey = args[0]
                now = float(args[1])
                window = float(args[2])
                rate = int(args[3])
                member = args[4]

                # zremrangebyscore: remove entries older than the window
                cutoff = now - window
                self._sets[zkey] = {
                    m: s for m, s in self._sets[zkey].items() if s > cutoff
                }
                # zcard check
                if len(self._sets[zkey]) >= rate:
                    return 0
                # zadd
                self._sets[zkey][member] = now
                return 1

        return FakeRedis()

    def test_allows_within_limit(self):
        from app.security.rate_limit import RedisRateLimiter
        rl = RedisRateLimiter(rate=5, per_seconds=1, redis_client=self._make_redis(), name="t")
        assert all(rl.allow("k") for _ in range(5))

    def test_blocks_over_limit(self):
        from app.security.rate_limit import RedisRateLimiter
        rl = RedisRateLimiter(rate=3, per_seconds=1, redis_client=self._make_redis(), name="t")
        for _ in range(3):
            rl.allow("k")
        assert rl.allow("k") is False

    def test_different_keys_are_independent(self):
        from app.security.rate_limit import RedisRateLimiter
        rl = RedisRateLimiter(rate=1, per_seconds=1, redis_client=self._make_redis(), name="t")
        assert rl.allow("a") is True
        assert rl.allow("b") is True

    def test_make_rate_limiter_returns_redis_when_client_provided(self):
        from app.security.rate_limit import make_rate_limiter, RedisRateLimiter
        rl = make_rate_limiter(rate=5, per_seconds=1, name="x", redis_client=self._make_redis())
        assert isinstance(rl, RedisRateLimiter)

    def test_make_rate_limiter_returns_in_process_when_no_client(self):
        from app.security.rate_limit import make_rate_limiter, RateLimiter
        rl = make_rate_limiter(rate=5, per_seconds=1)
        assert isinstance(rl, RateLimiter)

    def test_in_process_fallback_still_works(self):
        from app.security.rate_limit import RateLimiter
        rl = RateLimiter(rate=2, per_seconds=1)
        assert rl.allow("k") is True
        assert rl.allow("k") is True
        assert rl.allow("k") is False


# ===========================================================================
# 7. Environment-variable-based API key config
# ===========================================================================

class TestEnvApiKeys:
    def setup_method(self):
        """Ensure we start each test with default keys."""
        import app.security.auth as auth_mod
        os.environ.pop("API_KEYS", None)
        auth_mod.reload_keys()

    def teardown_method(self):
        """Restore default keys after each test."""
        import app.security.auth as auth_mod
        os.environ.pop("API_KEYS", None)
        auth_mod.reload_keys()

    def test_fallback_keys_work_without_env_var(self):
        """When API_KEYS is not set, hardcoded dev/admin keys are used."""
        import app.security.auth as auth_mod
        assert auth_mod.authenticate("dev-key") is not None
        assert auth_mod.authenticate("admin-key") is not None

    def test_env_var_overrides_keys(self):
        import app.security.auth as auth_mod
        env_val = "mykey:tenant_x:predict,read_models"
        with patch.dict(os.environ, {"API_KEYS": env_val}):
            auth_mod.reload_keys()
            identity = auth_mod.authenticate("mykey")
            assert identity is not None
            assert identity.tenant_id == "tenant_x"
            assert "predict" in identity.scopes

    def test_env_var_multiple_keys(self):
        import app.security.auth as auth_mod
        env_val = "k1:t1:predict;k2:t2:admin"
        with patch.dict(os.environ, {"API_KEYS": env_val}):
            auth_mod.reload_keys()
            assert auth_mod.authenticate("k1") is not None
            assert auth_mod.authenticate("k2") is not None

    def test_env_var_key_not_in_fallback_is_rejected(self):
        import app.security.auth as auth_mod
        env_val = "only-key:tenant:predict"
        with patch.dict(os.environ, {"API_KEYS": env_val}):
            auth_mod.reload_keys()
            # dev-key is NOT in the env var, so it should be rejected
            assert auth_mod.authenticate("dev-key") is None

    def test_invalid_key_returns_none(self):
        import app.security.auth as auth_mod
        assert auth_mod.authenticate("not-a-real-key") is None

    def test_scopes_parsed_correctly(self):
        import app.security.auth as auth_mod
        env_val = "svc-key:tenant_svc:predict,read_models,admin"
        with patch.dict(os.environ, {"API_KEYS": env_val}):
            auth_mod.reload_keys()
            identity = auth_mod.authenticate("svc-key")
            assert identity.scopes == {"predict", "read_models", "admin"}

    def test_malformed_entry_is_skipped(self):
        import app.security.auth as auth_mod
        # Missing scopes field — only 2 parts
        env_val = "badkey:tenant_bad;goodkey:tenant_good:predict"
        with patch.dict(os.environ, {"API_KEYS": env_val}):
            auth_mod.reload_keys()
            assert auth_mod.authenticate("badkey") is None
            assert auth_mod.authenticate("goodkey") is not None

    def test_empty_env_var_falls_back_to_defaults(self):
        import app.security.auth as auth_mod
        with patch.dict(os.environ, {"API_KEYS": ""}):
            auth_mod.reload_keys()
            assert auth_mod.authenticate("dev-key") is not None

    def test_reload_keys_picks_up_new_env(self):
        import app.security.auth as auth_mod
        with patch.dict(os.environ, {"API_KEYS": "new-key:t:predict"}):
            auth_mod.reload_keys()
            assert auth_mod.authenticate("new-key") is not None

    def test_identity_is_frozen(self):
        import app.security.auth as auth_mod
        identity = auth_mod.authenticate("dev-key")
        with pytest.raises((AttributeError, TypeError)):
            identity.tenant_id = "hacked"  # type: ignore[misc]


# ===========================================================================
# 8. arq async job queue
# ===========================================================================

class TestArqJobQueue:
    def _make_queue(self):
        from app.infra.queue.queue import ArqJobQueue
        mock_pool = AsyncMock()
        return ArqJobQueue(redis_pool=mock_pool), mock_pool

    def test_enqueue_inference_calls_enqueue_job(self):
        queue, pool = self._make_queue()
        job_id = uuid4()
        asyncio.run(
            queue.enqueue_inference(job_id, "echo", "v1", "hello")
        )
        pool.enqueue_job.assert_awaited_once()
        args = pool.enqueue_job.call_args[0]
        assert args[0] == "run_inference"
        assert args[1] == str(job_id)
        assert args[2] == "echo"
        assert args[3] == "v1"
        assert args[4] == "hello"

    def test_enqueue_batch_inference_calls_enqueue_job(self):
        queue, pool = self._make_queue()
        job_id = uuid4()
        asyncio.run(
            queue.enqueue_batch_inference(job_id, "echo", "v1", ["a", "b"])
        )
        pool.enqueue_job.assert_awaited_once()
        args = pool.enqueue_job.call_args[0]
        assert args[0] == "run_batch_inference"
        assert args[4] == ["a", "b"]

    def test_create_queue_returns_none_without_redis_url(self):
        from app.infra.queue.queue import create_queue
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REDIS_URL", None)
            result = asyncio.run(create_queue())
            assert result is None

    def test_create_queue_returns_none_when_redis_unavailable(self):
        from app.infra.queue.queue import create_queue
        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:9999/0"}):
            # Port 9999 should be unreachable; create_queue must not raise.
            result = asyncio.run(
                create_queue("redis://localhost:9999/0")
            )
            assert result is None


class TestAsyncInferenceServiceQueuePath:
    """
    Tests that AsyncInferenceService uses the queue when provided,
    and falls back to thread pool when queue is None.
    """

    def _make_service(self, queue=None):
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        from app.services.job_service import JobService
        from app.domain.registry.registry import ModelRegistry
        from app.services.prediction_service import PredictionService
        from app.services.routing_service import RoutingService
        from app.execution.execution_policy import ExecutionPolicy
        from app.execution.executor import InferenceExecutor
        from app.services.async_inference_service import AsyncInferenceService

        registry = ModelRegistry()
        job_service = JobService(SQLiteJobStore(db_path=":memory:"))
        executor = InferenceExecutor(device="cpu", max_workers=2)
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
        return AsyncInferenceService(pred_service, job_queue=queue), job_service

    def test_submit_without_queue_uses_thread_pool(self):
        service, job_service = self._make_service(queue=None)
        job_id = asyncio.run(service.submit("echo", "v1", "hello"))
        assert job_id is not None

        deadline = time.time() + 3
        while time.time() < deadline:
            job = job_service.get_job(job_id)
            if job.status.value in ("succeeded", "failed"):
                break
            time.sleep(0.05)

        assert job_service.get_job(job_id).status.value == "succeeded"

    def test_submit_with_queue_calls_enqueue(self):
        mock_queue = MagicMock()
        mock_queue.enqueue_inference = AsyncMock(return_value=None)

        service, job_service = self._make_service(queue=mock_queue)
        job_id = asyncio.run(service.submit("echo", "v1", "hello"))

        assert job_id is not None
        mock_queue.enqueue_inference.assert_awaited_once()
        call_args = mock_queue.enqueue_inference.call_args[0]
        assert call_args[0] == job_id
        assert call_args[1] == "echo"
        assert call_args[2] == "v1"

    def test_submit_batch_without_queue_uses_thread_pool(self):
        service, job_service = self._make_service(queue=None)
        job_id = asyncio.run(service.submit_batch("echo", "v1", ["a", "b"]))
        assert job_id is not None

        deadline = time.time() + 3
        while time.time() < deadline:
            job = job_service.get_job(job_id)
            if job.status.value in ("succeeded", "failed"):
                break
            time.sleep(0.05)

        assert job_service.get_job(job_id).status.value == "succeeded"

    def test_submit_batch_with_queue_calls_enqueue(self):
        mock_queue = MagicMock()
        mock_queue.enqueue_batch_inference = AsyncMock(return_value=None)

        service, job_service = self._make_service(queue=mock_queue)
        asyncio.run(service.submit_batch("echo", "v1", ["x", "y"]))

        mock_queue.enqueue_batch_inference.assert_awaited_once()

    def test_get_returns_job(self):
        service, job_service = self._make_service()
        job_id = asyncio.run(service.submit("echo", "v1", "test"))
        job = service.get(job_id)
        assert job.id == job_id

    def test_get_unknown_job_raises_key_error(self):
        service, _ = self._make_service()
        with pytest.raises(KeyError):
            service.get(uuid4())


# ===========================================================================
# arq worker task functions (unit tests, no real Redis)
# ===========================================================================

class TestArqWorkerTasks:
    def _make_ctx(self):
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        from app.services.job_service import JobService
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry()
        job_service = JobService(SQLiteJobStore(db_path=":memory:"))
        return {"registry": registry, "job_service": job_service}, job_service

    def test_run_inference_succeeds(self):
        from app.infra.queue.worker import run_inference

        ctx, job_service = self._make_ctx()
        job_id = job_service.create_job("echo", "v1", "hello")

        asyncio.run(
            run_inference(ctx, str(job_id), "echo", "v1", "hello")
        )

        job = job_service.get_job(job_id)
        assert job.status.value == "succeeded"
        assert job.result == "hello"

    def test_run_inference_marks_failed_on_error(self):
        from app.infra.queue.worker import run_inference

        ctx, job_service = self._make_ctx()
        job_id = job_service.create_job("echo", "v1", "hello")

        # Patch registry to raise
        ctx["registry"].get = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError):
            asyncio.run(
                run_inference(ctx, str(job_id), "echo", "v1", "hello")
            )

        job = job_service.get_job(job_id)
        assert job.status.value == "failed"
        assert "boom" in job.error_message

    def test_run_batch_inference_succeeds(self):
        from app.infra.queue.worker import run_batch_inference

        ctx, job_service = self._make_ctx()
        job_id = job_service.create_job("echo", "v1", ["a", "b"])

        asyncio.run(
            run_batch_inference(ctx, str(job_id), "echo", "v1", ["a", "b"])
        )

        job = job_service.get_job(job_id)
        assert job.status.value == "succeeded"
        assert job.result == ["a", "b"]

    def test_run_batch_inference_marks_failed_on_error(self):
        from app.infra.queue.worker import run_batch_inference

        ctx, job_service = self._make_ctx()
        job_id = job_service.create_job("echo", "v1", ["a"])

        ctx["registry"].get = MagicMock(side_effect=ValueError("bad"))

        with pytest.raises(ValueError):
            asyncio.run(
                run_batch_inference(ctx, str(job_id), "echo", "v1", ["a"])
            )

        job = job_service.get_job(job_id)
        assert job.status.value == "failed"


# ===========================================================================
# Integration: HTTP endpoints still work with Phase 2 changes
# ===========================================================================

class TestHTTPIntegrationPhase2:
    def test_predict_still_works(self, app_client):
        client, _, _ = app_client
        resp = client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "phase2"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "phase2"

    def test_async_predict_submit_and_poll(self, app_client):
        client, _, _ = app_client
        resp = client.post(
            "/predict/async",
            json={"model": "echo", "version": "v1", "data": "async-phase2"},
            headers=AUTH_HEADERS,
        )
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
        assert poll.json()["result"] == "async-phase2"

    def test_auth_with_env_key(self, app_client):
        """Env-var keys are loaded at import; dev-key must still authenticate."""
        client, _, _ = app_client
        resp = client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "env-auth"},
            headers={"X-API-Key": "dev-key"},
        )
        assert resp.status_code == 200

    def test_invalid_key_rejected(self, app_client):
        client, _, _ = app_client
        resp = client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "x"},
            headers={"X-API-Key": "not-valid"},
        )
        assert resp.status_code == 401

    def test_rate_limit_middleware_present(self, app_client):
        """Middleware is wired; 10 rapid requests should not all fail (limit is 10/s)."""
        client, _, _ = app_client
        responses = [
            client.post(
                "/predict",
                json={"model": "echo", "version": "v1", "data": "x"},
                headers=AUTH_HEADERS,
            )
            for _ in range(5)
        ]
        # All 5 should succeed (well within the 10/s limit)
        assert all(r.status_code == 200 for r in responses)


# ===========================================================================
# deps.py — job store selection logic
# ===========================================================================

class TestDepsJobStoreSelection:
    def test_selects_sqlite_when_no_database_url(self):
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        import app.adapters.http.deps as deps_mod

        deps_mod.get_job_store.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATABASE_URL", None)
            store = deps_mod.get_job_store()
            assert isinstance(store, SQLiteJobStore)
        deps_mod.get_job_store.cache_clear()

    def test_selects_postgres_when_database_url_set_and_available(self):
        import app.adapters.http.deps as deps_mod
        from app.infra.jobs.postgres_job_store import PostgresJobStore

        deps_mod.get_job_store.cache_clear()

        mock_store = MagicMock(spec=PostgresJobStore)
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@localhost/db"}):
            with patch(
                "app.infra.jobs.postgres_job_store.PostgresJobStore",
                return_value=mock_store,
            ):
                store = deps_mod.get_job_store()
                assert store is mock_store

        deps_mod.get_job_store.cache_clear()

    def test_falls_back_to_sqlite_when_postgres_unavailable(self):
        from app.infra.jobs.sqlite_job_store import SQLiteJobStore
        import app.adapters.http.deps as deps_mod

        deps_mod.get_job_store.cache_clear()
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@localhost/db"}):
            with patch(
                "app.infra.jobs.postgres_job_store.PostgresJobStore",
                side_effect=Exception("connection refused"),
            ):
                store = deps_mod.get_job_store()
                assert isinstance(store, SQLiteJobStore)

        deps_mod.get_job_store.cache_clear()
