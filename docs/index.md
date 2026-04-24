# Inference Engine — Documentation

A task-agnostic, framework-independent ML serving backend designed for production inference workloads.

---

## Documentation Index

| Document | Description |
|---|---|
| [Architecture](./architecture.md) | System design, layers, invariants, and data flow |
| [API Reference](./api-reference.md) | All HTTP endpoints, request/response schemas, auth |
| [Domain Model](./domain-model.md) | Core abstractions: Model, Pipeline, Registry, Jobs |
| [Configuration](./configuration.md) | Routing strategies, execution policy, environment setup |
| [Security](./security.md) | Authentication, authorization, rate limiting, payload guards |
| [Observability](./observability.md) | Prometheus metrics, structured logging |
| [Adding a Model](./adding-a-model.md) | Step-by-step guide to registering a new model |
| [Development Guide](./development.md) | Setup, running locally, project conventions |
| [Assessment & Roadmap](./assessment.md) | Expert rating, known issues, and prioritized improvement roadmap |

---

## Quick Start

```bash
# Install dependencies
pip install -e .

# Run the server
uvicorn app.adapters.http.app:app --reload

# Health check
curl http://localhost:8000/health

# Predict (requires API key)
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": {"x": 42}}'
```

---

## Core Concepts at a Glance

```
Client Request
    ↓
HTTP Adapter (FastAPI)
    ↓
PredictionService
    ↓
RoutingService  →  resolves (model, version)
    ↓
ModelRegistry   →  loads / caches InferencePipeline
    ↓
ExecutionPolicy →  selects InferenceExecutor (cpu/gpu)
    ↓
InferencePipeline: Preprocessor → Model → Postprocessor
    ↓
JobService      →  persists job state (SQLite)
    ↓
Response
```
