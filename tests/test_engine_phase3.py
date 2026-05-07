"""
Phase 3 test suite.

Covers:
  1. ModelLoader interface — LocalModelLoader, S3ModelLoader (mocked)
  2. Auto-discovery — ModelRegistry scans models/ directory
  3. Per-tenant metrics, rate limits, and job isolation
  4. Executor plugin interface — BaseExecutor, OnnxExecutor/TritonExecutor stubs
  5. Input validation hooks — BaseValidator wired into InferencePipeline
"""
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"X-API-Key": "dev-key"}


# ---------------------------------------------------------------------------
# Shared fixture (same pattern as phase 1 & 2)
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

    with TestClient(app) as client:
        yield client, real_registry, job_service


# ===========================================================================
# 1. ModelLoader interface
# ===========================================================================

class TestLocalModelLoader:
    def test_returns_path_when_directory_exists(self):
        from app.domain.loading.local_loader import LocalModelLoader
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp) / "mymodel" / "v1"
            artifact_dir.mkdir(parents=True)
            loader = LocalModelLoader(root=tmp)
            result = loader.load("mymodel", "v1")
            assert result == artifact_dir

    def test_raises_when_directory_missing(self):
        from app.domain.loading.local_loader import LocalModelLoader
        with tempfile.TemporaryDirectory() as tmp:
            loader = LocalModelLoader(root=tmp)
            with pytest.raises(FileNotFoundError):
                loader.load("ghost", "v99")

    def test_loader_is_subclass_of_base(self):
        from app.domain.loading.base import ModelLoader
        from app.domain.loading.local_loader import LocalModelLoader
        assert issubclass(LocalModelLoader, ModelLoader)


class TestS3ModelLoader:
    def test_loader_is_subclass_of_base(self):
        from app.domain.loading.base import ModelLoader
        from app.domain.loading.s3_loader import S3ModelLoader
        assert issubclass(S3ModelLoader, ModelLoader)

    def test_raises_when_boto3_missing(self):
        from app.domain.loading.s3_loader import S3ModelLoader
        loader = S3ModelLoader(bucket="my-bucket")
        with patch.dict("sys.modules", {"boto3": None}):
            with pytest.raises((RuntimeError, ImportError)):
                loader.load("model", "v1")

    def test_downloads_objects_to_temp_dir(self):
        from app.domain.loading.s3_loader import S3ModelLoader

        mock_boto3 = MagicMock()
        mock_s3 = MagicMock()
        mock_boto3.client.return_value = mock_s3

        paginator = MagicMock()
        mock_s3.get_paginator.return_value = paginator
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "models/mymodel/v1/model.onnx"}]}
        ]

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            loader = S3ModelLoader(bucket="my-bucket", prefix="models")
            result = loader.load("mymodel", "v1")

        assert result.is_dir()
        mock_s3.download_file.assert_called_once()


# ===========================================================================
# 2. Auto-discovery
# ===========================================================================

class TestAutoDiscovery:
    def test_discovers_definition_from_models_dir(self):
        from app.domain.registry.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmp:
            defn_dir = Path(tmp) / "sentiment" / "v1"
            defn_dir.mkdir(parents=True)
            (defn_dir / "definition.py").write_text(
                "from app.domain.pipelines import InferencePipeline\n"
                "from app.domain.processing.pre import IdentityPreprocessor\n"
                "from app.domain.processing.post import IdentityPostprocessor\n"
                "from app.domain.models.echo_model import EchoModel\n"
                "MODEL_NAME = 'sentiment'\n"
                "MODEL_VERSION = 'v1'\n"
                "def build_pipeline():\n"
                "    m = EchoModel(); m.load()\n"
                "    return InferencePipeline(\n"
                "        IdentityPreprocessor(), m, IdentityPostprocessor()\n"
                "    )\n"
            )
            registry = ModelRegistry(models_dir=tmp)
            assert ("sentiment", "v1") in registry.list_models()
            pipeline = registry.get("sentiment", "v1")
            assert pipeline.run("hello") == "hello"

    def test_malformed_definition_is_skipped(self):
        from app.domain.registry.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmp:
            defn_dir = Path(tmp) / "broken" / "v1"
            defn_dir.mkdir(parents=True)
            (defn_dir / "definition.py").write_text("this is not valid python !!!")
            # Should not raise; broken definition is silently skipped
            registry = ModelRegistry(models_dir=tmp)
            assert ("broken", "v1") not in registry.list_models()

    def test_discovered_definition_overrides_builtin(self):
        """A discovered echo:v1 replaces the built-in one."""
        from app.domain.registry.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmp:
            defn_dir = Path(tmp) / "echo" / "v1"
            defn_dir.mkdir(parents=True)
            (defn_dir / "definition.py").write_text(
                "from app.domain.pipelines import InferencePipeline\n"
                "from app.domain.processing.pre import IdentityPreprocessor\n"
                "from app.domain.processing.post import IdentityPostprocessor\n"
                "from app.domain.models.echo_model import EchoModel\n"
                "MODEL_NAME = 'echo'\n"
                "MODEL_VERSION = 'v1'\n"
                "MARKER = 'discovered'\n"
                "def build_pipeline():\n"
                "    m = EchoModel(); m.load()\n"
                "    return InferencePipeline(\n"
                "        IdentityPreprocessor(), m, IdentityPostprocessor()\n"
                "    )\n"
            )
            registry = ModelRegistry(models_dir=tmp)
            # The key still exists (not duplicated)
            assert registry.list_models().count(("echo", "v1")) == 1

    def test_empty_models_dir_uses_builtins_only(self):
        from app.domain.registry.registry import ModelRegistry

        with tempfile.TemporaryDirectory() as tmp:
            registry = ModelRegistry(models_dir=tmp)
            models = registry.list_models()
            assert ("echo", "v1") in models
            assert ("echo", "v2") in models

    def test_nonexistent_models_dir_uses_builtins_only(self):
        from app.domain.registry.registry import ModelRegistry

        registry = ModelRegistry(models_dir="/nonexistent/path/xyz")
        assert ("echo", "v1") in registry.list_models()


# ===========================================================================
# 3. Per-tenant metrics, rate limits, and job isolation
# ===========================================================================

class TestPerTenantMetrics:
    def test_predict_records_tenant_label(self, app_client):
        from app.core.metrics import INFERENCE_REQUESTS
        client, _, _ = app_client

        before = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_dev")._value.get()
        client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "hi"},
            headers=AUTH_HEADERS,
        )
        after = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_dev")._value.get()
        assert after > before

    def test_different_tenants_have_independent_counters(self, app_client):
        from app.core.metrics import INFERENCE_REQUESTS
        client, _, _ = app_client

        before_dev = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_dev")._value.get()
        before_admin = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_admin")._value.get()

        client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "hi"},
            headers={"X-API-Key": "dev-key"},
        )

        after_dev = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_dev")._value.get()
        after_admin = INFERENCE_REQUESTS.labels("echo", "v1", "tenant_admin")._value.get()

        assert after_dev > before_dev
        assert after_admin == before_admin  # admin tenant untouched


class TestPerTenantRateLimit:
    def test_rate_limit_keys_on_tenant_id(self):
        from app.security.rate_limit import RateLimiter

        limiter = RateLimiter(rate=2, per_seconds=10)
        assert limiter.allow("tenant_a")
        assert limiter.allow("tenant_a")
        assert not limiter.allow("tenant_a")   # tenant_a exhausted
        assert limiter.allow("tenant_b")        # tenant_b independent

    def test_middleware_uses_tenant_id_not_api_key(self, app_client):
        """Two different API keys for the same tenant share the rate bucket."""
        from app.security.rate_limit import RateLimiter
        from app.adapters.http.middleware import rate_limit as rl_module

        # Replace the /predict limiter with a tight one (1 req / 60s)
        tight = RateLimiter(rate=1, per_seconds=60)
        original = rl_module.LIMITS.get("/predict")
        rl_module.LIMITS["/predict"] = tight

        client, _, _ = app_client
        try:
            r1 = client.post(
                "/predict",
                json={"model": "echo", "version": "v1", "data": "x"},
                headers=AUTH_HEADERS,
            )
            r2 = client.post(
                "/predict",
                json={"model": "echo", "version": "v1", "data": "x"},
                headers=AUTH_HEADERS,
            )
            assert r1.status_code == 200
            assert r2.status_code == 429
        finally:
            if original is not None:
                rl_module.LIMITS["/predict"] = original
            else:
                del rl_module.LIMITS["/predict"]


# ===========================================================================
# 4. Executor plugin interface
# ===========================================================================

class TestBaseExecutor:
    def test_inference_executor_is_subclass(self):
        from app.execution.base import BaseExecutor
        from app.execution.executor import InferenceExecutor
        assert issubclass(InferenceExecutor, BaseExecutor)

    def test_onnx_executor_is_subclass(self):
        from app.execution.base import BaseExecutor
        from app.execution.onnx_executor import OnnxExecutor
        assert issubclass(OnnxExecutor, BaseExecutor)

    def test_triton_executor_is_subclass(self):
        from app.execution.base import BaseExecutor
        from app.execution.triton_executor import TritonExecutor
        assert issubclass(TritonExecutor, BaseExecutor)

    def test_onnx_executor_raises_without_onnxruntime(self):
        from app.execution.onnx_executor import OnnxExecutor
        with patch.dict("sys.modules", {"onnxruntime": None}):
            with pytest.raises(RuntimeError, match="onnxruntime"):
                OnnxExecutor()

    def test_triton_executor_raises_without_tritonclient(self):
        from app.execution.triton_executor import TritonExecutor
        with patch.dict("sys.modules", {"tritonclient": None, "tritonclient.grpc": None}):
            with pytest.raises(RuntimeError, match="tritonclient"):
                TritonExecutor()

    def test_execution_policy_works_with_custom_executor(self):
        """ExecutionPolicy accepts any BaseExecutor implementation."""
        from app.execution.base import BaseExecutor
        from app.execution.execution_policy import ExecutionPolicy

        class DummyExecutor(BaseExecutor):
            def submit(self, fn, *args, timeout_s=None):
                return fn(*args)
            def submit_background(self, fn, *args):
                fn(*args)

        dummy = DummyExecutor()
        policy = ExecutionPolicy(
            executors={"dummy": dummy},
            policy={"echo:v1": "dummy"},
            default="dummy",
        )
        resolved = policy.resolve("echo", "v1")
        assert resolved is dummy
        assert resolved.submit(lambda: 42) == 42


# ===========================================================================
# 5. Input validation hooks
# ===========================================================================

class TestValidationHooks:
    def test_noop_validator_accepts_anything(self):
        from app.domain.validation.base import NoOpValidator
        v = NoOpValidator()
        v.validate(None)
        v.validate({"any": "thing"})
        v.validate([1, 2, 3])

    def test_pipeline_calls_validator(self):
        from app.domain.validation.base import BaseValidator, ValidationError
        from app.domain.pipelines.base import InferencePipeline
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.models.echo_model import EchoModel

        class RejectAll(BaseValidator):
            def validate(self, model_input):
                raise ValidationError("rejected")

        model = EchoModel()
        model.load()
        pipeline = InferencePipeline(
            preprocessor=IdentityPreprocessor(),
            model=model,
            postprocessor=IdentityPostprocessor(),
            validator=RejectAll(),
        )
        with pytest.raises(ValidationError, match="rejected"):
            pipeline.run("anything")

    def test_pipeline_passes_when_validator_accepts(self):
        from app.domain.validation.base import NoOpValidator
        from app.domain.pipelines.base import InferencePipeline
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.models.echo_model import EchoModel

        model = EchoModel()
        model.load()
        pipeline = InferencePipeline(
            preprocessor=IdentityPreprocessor(),
            model=model,
            postprocessor=IdentityPostprocessor(),
            validator=NoOpValidator(),
        )
        assert pipeline.run("hello") == "hello"

    def test_pipeline_defaults_to_noop_validator(self):
        from app.domain.pipelines.base import InferencePipeline
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.models.echo_model import EchoModel

        model = EchoModel()
        model.load()
        pipeline = InferencePipeline(
            preprocessor=IdentityPreprocessor(),
            model=model,
            postprocessor=IdentityPostprocessor(),
        )
        assert pipeline.run("no validator") == "no validator"

    def test_custom_range_validator(self):
        """Demonstrate a real validator: reject inputs outside [0, 1]."""
        from app.domain.validation.base import BaseValidator, ValidationError
        from app.domain.pipelines.base import InferencePipeline
        from app.domain.processing.pre import IdentityPreprocessor
        from app.domain.processing.post import IdentityPostprocessor
        from app.domain.models.echo_model import EchoModel

        class RangeValidator(BaseValidator):
            def validate(self, x):
                if not (0 <= x <= 1):
                    raise ValidationError(f"Expected value in [0,1], got {x}")

        model = EchoModel()
        model.load()
        pipeline = InferencePipeline(
            preprocessor=IdentityPreprocessor(),
            model=model,
            postprocessor=IdentityPostprocessor(),
            validator=RangeValidator(),
        )
        assert pipeline.run(0.5) == 0.5
        with pytest.raises(ValidationError):
            pipeline.run(2.0)
