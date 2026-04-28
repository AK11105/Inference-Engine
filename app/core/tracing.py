"""
OpenTelemetry distributed tracing.

Instruments the FastAPI app with OTLP export when OTEL_EXPORTER_OTLP_ENDPOINT
is set. Falls back to a no-op tracer when the SDK is not installed or the
endpoint is absent — callers never need to guard against ImportError.

Usage:
    from app.core.tracing import get_tracer, setup_tracing

    setup_tracing(app)          # call once in create_app()
    tracer = get_tracer()       # use anywhere
    with tracer.start_as_current_span("my-span") as span:
        span.set_attribute("model", "echo")
"""
import os
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy import helpers — opentelemetry-sdk is optional
# ---------------------------------------------------------------------------

def _otel_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        return True
    except ImportError:
        return False


def setup_tracing(app=None) -> None:
    """
    Configure the global TracerProvider.

    When OTEL_EXPORTER_OTLP_ENDPOINT is set and opentelemetry-sdk is installed,
    spans are exported via OTLP/gRPC.  Otherwise a no-op provider is used.
    """
    if not _otel_available():
        return

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.environ.get("OTEL_SERVICE_NAME", "inference-engine")

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            pass  # OTLP exporter not installed — traces still collected locally

    trace.set_tracer_provider(provider)

    # Instrument FastAPI if available
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass


def get_tracer(name: str = "inference_engine"):
    """
    Return a tracer.  Always safe to call — returns a no-op tracer when
    opentelemetry is not installed.
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


# ---------------------------------------------------------------------------
# Minimal no-op tracer so callers don't need try/except
# ---------------------------------------------------------------------------

class _NoOpSpan:
    def set_attribute(self, key, value): pass
    def record_exception(self, exc): pass
    def set_status(self, *a, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _NoOpTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoOpSpan()

    def start_span(self, name, **kwargs):
        return _NoOpSpan()
