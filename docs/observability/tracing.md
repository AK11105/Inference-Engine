# Distributed Tracing

**File:** `app/core/tracing.py`

The engine instruments every inference request with an OpenTelemetry span. The SDK is optional — a no-op tracer is used when it is not installed, so no code changes are needed to run without tracing.

---

## Setup

Tracing is initialised once in `create_app()`:

```python
from app.core.tracing import setup_tracing
setup_tracing(app)
```

When `OTEL_EXPORTER_OTLP_ENDPOINT` is set and `opentelemetry-sdk` is installed, spans are exported via OTLP/gRPC. Otherwise they are collected locally (useful with a local Jaeger or OTLP collector).

---

## Environment variables

| Variable | Description |
|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP/gRPC endpoint, e.g. `http://localhost:4317` |
| `OTEL_SERVICE_NAME` | Service name in traces (default: `inference-engine`) |

---

## Span attributes

Every inference span (`inference:{model}:{version}`) carries:

| Attribute | Value |
|---|---|
| `model` | Model name |
| `version` | Model version |
| `tenant_id` | Tenant from the API key |
| `request_id` | `X-Request-ID` header value |
| `latency_ms` | End-to-end latency in milliseconds |

Exceptions are recorded on the span via `span.record_exception()`.

---

## Installing the SDK

```bash
pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc opentelemetry-instrumentation-fastapi
```

Without these packages the engine runs normally — all tracing calls are no-ops.

---

## Using the tracer in custom code

```python
from app.core.tracing import get_tracer

tracer = get_tracer()
with tracer.start_as_current_span("my-custom-span") as span:
    span.set_attribute("key", "value")
    # ... do work
```

`get_tracer()` always returns a usable object — either a real OTel tracer or the built-in no-op.
