"""
Inference Playground — test suite.

Tests cover:
1. Route mounting and static file serving
2. Auth bypass for playground paths
3. HTML page structure and content
4. Static asset accessibility (JS, CSS)
5. API endpoints still require auth (no accidental bypass)
6. Playground integration with /predict and /models APIs
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

AUTH_HEADERS = {"X-API-Key": "dev-key"}

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client():
    """Full app with playground mounted, wired to in-memory stores."""
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

    real_registry.warm_up()

    app = create_app()
    app.dependency_overrides[deps.get_registry] = lambda: real_registry
    app.dependency_overrides[deps.get_job_service] = lambda: job_service
    app.dependency_overrides[deps.get_async_service] = lambda: async_service

    deps._job_store = job_service._store
    try:
        with patch.dict(os.environ, {"REDIS_URL": "", "DATABASE_URL": ""}, clear=False):
            with TestClient(app) as client:
                yield client
    finally:
        deps._job_store = None


# ---------------------------------------------------------------------------
# Test: Static files exist on disk
# ---------------------------------------------------------------------------


class TestStaticFilesExist:
    """Verify the static playground assets are present in the expected location."""

    STATIC_DIR = Path(__file__).parent.parent / "app" / "static" / "playground"

    def test_static_directory_exists(self):
        assert self.STATIC_DIR.is_dir(), f"Missing: {self.STATIC_DIR}"

    def test_index_html_exists(self):
        assert (self.STATIC_DIR / "index.html").is_file()

    def test_playground_js_exists(self):
        assert (self.STATIC_DIR / "playground.js").is_file()

    def test_playground_css_exists(self):
        assert (self.STATIC_DIR / "playground.css").is_file()


# ---------------------------------------------------------------------------
# Test: Route mounting — /playground serves HTML
# ---------------------------------------------------------------------------


class TestPlaygroundRoute:
    """The /playground endpoint serves the interactive UI."""

    def test_playground_returns_200(self, app_client):
        resp = app_client.get("/playground")
        assert resp.status_code == 200

    def test_playground_trailing_slash_returns_200(self, app_client):
        resp = app_client.get("/playground/")
        assert resp.status_code == 200

    def test_playground_returns_html_content_type(self, app_client):
        resp = app_client.get("/playground")
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type

    def test_playground_html_contains_title(self, app_client):
        resp = app_client.get("/playground")
        assert "Inference Playground" in resp.text

    def test_playground_html_references_js(self, app_client):
        resp = app_client.get("/playground")
        assert "playground.js" in resp.text

    def test_playground_html_references_css(self, app_client):
        resp = app_client.get("/playground")
        assert "playground.css" in resp.text


# ---------------------------------------------------------------------------
# Test: Static asset serving (JS, CSS)
# ---------------------------------------------------------------------------


class TestStaticAssetServing:
    """Static assets are served at /playground/playground.{js,css}."""

    def test_js_returns_200(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert resp.status_code == 200

    def test_js_content_type(self, app_client):
        resp = app_client.get("/playground/playground.js")
        content_type = resp.headers.get("content-type", "")
        assert "javascript" in content_type or "text/javascript" in content_type

    def test_css_returns_200(self, app_client):
        resp = app_client.get("/playground/playground.css")
        assert resp.status_code == 200

    def test_css_content_type(self, app_client):
        resp = app_client.get("/playground/playground.css")
        content_type = resp.headers.get("content-type", "")
        assert "text/css" in content_type

    def test_nonexistent_static_file_returns_404(self, app_client):
        resp = app_client.get("/playground/nonexistent.xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Auth bypass — playground loads without API key
# ---------------------------------------------------------------------------


class TestPlaygroundAuthBypass:
    """Playground paths do NOT require authentication."""

    def test_playground_no_auth_required(self, app_client):
        # No X-API-Key header
        resp = app_client.get("/playground")
        assert resp.status_code == 200

    def test_playground_js_no_auth_required(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert resp.status_code == 200

    def test_playground_css_no_auth_required(self, app_client):
        resp = app_client.get("/playground/playground.css")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test: API endpoints STILL require auth (no accidental bypass)
# ---------------------------------------------------------------------------


class TestAPIAuthNotBypassed:
    """Ensure playground auth exemption doesn't leak to API endpoints."""

    def test_predict_still_requires_auth(self, app_client):
        resp = app_client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "hi"},
        )
        assert resp.status_code == 401

    def test_models_still_requires_auth(self, app_client):
        resp = app_client.get("/models")
        assert resp.status_code == 401

    def test_predict_works_with_auth(self, app_client):
        resp = app_client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "hello"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "hello"

    def test_models_works_with_auth(self, app_client):
        resp = app_client.get("/models", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) > 0


# ---------------------------------------------------------------------------
# Test: HTML page structure — key UI elements present
# ---------------------------------------------------------------------------


class TestPlaygroundHTMLStructure:
    """The playground HTML includes the required UI components."""

    def test_has_api_key_input(self, app_client):
        resp = app_client.get("/playground")
        # Should have an input for API key
        assert "api-key" in resp.text.lower() or "apikey" in resp.text.lower() or "api_key" in resp.text.lower()

    def test_has_model_selector(self, app_client):
        resp = app_client.get("/playground")
        assert "model" in resp.text.lower()

    def test_has_predict_button(self, app_client):
        resp = app_client.get("/playground")
        assert "predict" in resp.text.lower() or "Predict" in resp.text

    def test_has_input_area(self, app_client):
        resp = app_client.get("/playground")
        # Should have textarea or input for data
        assert "textarea" in resp.text.lower() or "input" in resp.text.lower()

    def test_has_response_display(self, app_client):
        resp = app_client.get("/playground")
        assert "response" in resp.text.lower() or "result" in resp.text.lower() or "output" in resp.text.lower()

    def test_has_history_section(self, app_client):
        resp = app_client.get("/playground")
        assert "history" in resp.text.lower()

    def test_has_code_snippets_section(self, app_client):
        resp = app_client.get("/playground")
        # Should reference curl/python/js snippets
        assert "snippet" in resp.text.lower() or "curl" in resp.text.lower()

    def test_has_json_input_mode(self, app_client):
        resp = app_client.get("/playground")
        assert "json" in resp.text.lower()

    def test_has_text_input_mode(self, app_client):
        resp = app_client.get("/playground")
        assert "text" in resp.text.lower()

    def test_has_csv_input_mode(self, app_client):
        resp = app_client.get("/playground")
        assert "csv" in resp.text.lower()

    def test_has_latency_display(self, app_client):
        resp = app_client.get("/playground")
        assert "latency" in resp.text.lower() or "ms" in resp.text.lower()

    def test_no_external_cdn_dependencies(self, app_client):
        """Playground must work offline — no CDN links."""
        resp = app_client.get("/playground")
        html = resp.text
        # Should not reference any CDN
        assert "cdn.jsdelivr.net" not in html
        assert "cdnjs.cloudflare.com" not in html
        assert "unpkg.com" not in html
        assert "googleapis.com" not in html


# ---------------------------------------------------------------------------
# Test: JavaScript contains required functionality
# ---------------------------------------------------------------------------


class TestPlaygroundJSContent:
    """The playground JS file contains required logic."""

    def test_js_has_predict_function(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "predict" in resp.text.lower()

    def test_js_has_localstorage_usage(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "localStorage" in resp.text

    def test_js_has_fetch_call(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "fetch" in resp.text

    def test_js_has_model_loading(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "/models" in resp.text

    def test_js_has_curl_snippet_generation(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "curl" in resp.text

    def test_js_has_python_snippet_generation(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "python" in resp.text.lower() or "requests" in resp.text

    def test_js_has_javascript_snippet_generation(self, app_client):
        resp = app_client.get("/playground/playground.js")
        # JS snippet generation references fetch
        assert "fetch" in resp.text

    def test_js_has_csv_handling(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "csv" in resp.text.lower() or "CSV" in resp.text

    def test_js_has_latency_measurement(self, app_client):
        resp = app_client.get("/playground/playground.js")
        # Should measure time/performance
        assert "performance" in resp.text.lower() or "Date.now" in resp.text or "time" in resp.text.lower()

    def test_js_has_history_management(self, app_client):
        resp = app_client.get("/playground/playground.js")
        assert "history" in resp.text.lower()

    def test_js_has_benchmark_functionality(self, app_client):
        resp = app_client.get("/playground/playground.js")
        # Should have benchmarking (p50/p95/p99 or similar)
        assert "benchmark" in resp.text.lower() or "p50" in resp.text or "percentile" in resp.text.lower()


# ---------------------------------------------------------------------------
# Test: CSS contains playground styles
# ---------------------------------------------------------------------------


class TestPlaygroundCSSContent:
    """The playground CSS provides styling."""

    def test_css_is_not_empty(self, app_client):
        resp = app_client.get("/playground/playground.css")
        assert len(resp.text.strip()) > 100

    def test_css_has_playground_styles(self, app_client):
        resp = app_client.get("/playground/playground.css")
        # Should target playground-specific elements
        assert "playground" in resp.text.lower() or "container" in resp.text.lower()


# ---------------------------------------------------------------------------
# Test: Existing routes unaffected (regression)
# ---------------------------------------------------------------------------


class TestExistingRoutesUnaffected:
    """Verify playground addition doesn't break existing functionality."""

    def test_health_still_works(self, app_client):
        resp = app_client.get("/health")
        assert resp.status_code == 200

    def test_ready_still_works(self, app_client):
        resp = app_client.get("/ready")
        assert resp.status_code == 200

    def test_docs_still_works(self, app_client):
        """FastAPI's built-in OpenAPI docs still accessible."""
        resp = app_client.get("/docs")
        assert resp.status_code == 200

    def test_predict_echo_still_works(self, app_client):
        resp = app_client.post(
            "/predict",
            json={"model": "echo", "version": "v1", "data": "test"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "test"

    def test_metrics_still_works(self, app_client):
        resp = app_client.get("/metrics")
        assert resp.status_code == 200
