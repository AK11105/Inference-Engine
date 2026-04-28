# Documentation

## Architecture
| | |
|---|---|
| [Overview](architecture/overview.md) | Layers, invariants, dependency injection |
| [Request Flow](architecture/request-flow.md) | Sync + async call stacks, middleware order |

## Components
| | |
|---|---|
| [ModelRegistry](components/model-registry.md) | Thread-safe pipeline cache, LRU eviction, auto-discovery, hot-reload |
| [InferencePipeline](components/inference-pipeline.md) | Model, Preprocessor, Postprocessor, Validator |
| [Execution Engine](components/execution-engine.md) | InferenceExecutor, OnnxExecutor, TritonExecutor, ExecutionPolicy |
| [Routing Service](components/routing-service.md) | Static, canary, A/B version resolution |
| [Job System](components/job-system.md) | Job lifecycle, JobService, SQLite/Postgres stores |
| [Async Queue](components/async-queue.md) | AsyncInferenceService, arq worker, Redis fallback |
| [Artifact Loaders](components/artifact-loaders.md) | LocalModelLoader, S3ModelLoader |

## API
| | |
|---|---|
| [Inference](api/inference.md) | `/predict`, `/predict/batch`, `/predict/async*` |
| [Jobs](api/jobs.md) | `/jobs/{id}` |
| [System](api/system.md) | `/health`, `/ready`, `/models`, `/metrics`, `/debug/*` |
| [Admin](api/admin.md) | `/admin/models/*/reload`, `/admin/models/memory` |

## Guides
| | |
|---|---|
| [Getting Started](guides/getting-started.md) | Install, run, first request |
| [Adding a Model](guides/adding-a-model.md) | Step-by-step with checklist |
| [Development](guides/development.md) | Tests, curl commands, common issues |

## Configuration
| | |
|---|---|
| [Environment Variables](configuration/environment.md) | `API_KEYS`, `DATABASE_URL`, `REDIS_URL`, `OTEL_*` |
| [Routing](configuration/routing.md) | Static, canary, A/B rules |
| [Execution](configuration/execution.md) | Executor assignment per model:version |
| [SLA Timeouts](configuration/sla.md) | Per-model timeout budgets |

## Security
| | |
|---|---|
| [Authentication](security/auth.md) | API keys, scopes, production checklist |
| [Rate Limiting](security/rate-limiting.md) | Sliding window, Redis vs in-process, payload guard |

## Observability
| | |
|---|---|
| [Logging](observability/logging.md) | JSON structured logs, request ID propagation |
| [Metrics](observability/metrics.md) | Prometheus metrics reference, alerting |
| [Tracing](observability/tracing.md) | OpenTelemetry distributed tracing |
