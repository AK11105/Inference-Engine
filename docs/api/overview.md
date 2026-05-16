# API Reference

## Base URL

```
http://localhost:8000
```

## Authentication

All endpoints except public ones require:

```
X-API-Key: <your-api-key>
```

## Endpoints

| Method | Path | Scope | Description |
|---|---|---|---|
| `POST` | `/predict` | `predict` | Synchronous inference |
| `POST` | `/predict/batch` | `predict` | Batch inference |
| `POST` | `/predict/async` | `predict` | Submit async job |
| `GET` | `/predict/async/{job_id}` | *(any)* | Poll async job status |
| `GET` | `/jobs/{job_id}` | *(any)* | Get job record |
| `GET` | `/models` | `read_models` | List registered models |
| `GET` | `/health` | none | Liveness check |
| `GET` | `/ready` | none | Readiness check |
| `GET` | `/metrics` | none | Prometheus metrics |
| `GET` | `/debug/models/loaded` | `admin` | Currently loaded pipelines |
| `POST` | `/admin/models/{name}/{version}/reload` | `admin` | Hot-reload a pipeline |
| `GET` | `/admin/models/memory` | `admin` | Memory usage per pipeline |

## Sections

- [Inference](inference.md) — `/predict`, `/predict/batch`, `/predict/async*`
- [Jobs](jobs.md) — `/jobs/{id}`
- [Models](models.md) — `/models`
- [Admin](admin.md) — `/admin/*`, `/debug/*`
- [System](system.md) — `/health`, `/ready`, `/metrics`
