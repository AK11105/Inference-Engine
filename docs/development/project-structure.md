# Project Structure

![Layer dependency diagram](../assets/layer-dependency-light.png#only-light)
![Layer dependency diagram](../assets/layer-dependency-dark.png#only-dark)

```
inference-engine/
├── app/
│   ├── adapters/
│   │   └── http/               # FastAPI routes, middleware, schemas, deps
│   ├── services/               # Orchestration: PredictionService, AsyncInferenceService
│   ├── domain/
│   │   ├── models/             # BaseModel and model implementations
│   │   ├── pipelines/          # InferencePipeline
│   │   ├── processing/         # Preprocessors and postprocessors
│   │   ├── validation/         # Validators
│   │   ├── jobs/               # Job dataclass, JobStatus, JobStore interface
│   │   ├── registry/           # ModelRegistry
│   │   ├── loading/            # LocalModelLoader, S3ModelLoader
│   │   └── definitions/        # Built-in model definitions (echo)
│   ├── execution/              # InferenceExecutor, OnnxExecutor, TritonExecutor, ExecutionPolicy
│   ├── infra/
│   │   ├── jobs/               # SQLiteJobStore, PostgresJobStore
│   │   └── queue/              # ArqJobQueue, arq worker
│   ├── config/                 # routing.py, execution.py, sla.py
│   ├── security/               # Auth, rate limiting
│   ├── core/                   # Metrics, logging, tracing
│   └── cli/                    # deploy and fix commands
├── deploy/
│   ├── prometheus/
│   │   └── prometheus.yml      # Scrape config (targets api:8000 every 15s)
│   └── grafana/
│       └── provisioning/
│           ├── datasources/
│           │   └── prometheus.yml          # Auto-provisions Prometheus datasource
│           └── dashboards/
│               ├── dashboards.yml          # Provider config — loads JSON files from this dir
│               └── inference-engine.json   # Pre-built dashboard (all metrics)
├── models/                     # Auto-discovered model definitions
├── model_artifacts/            # Binary artifacts (weights, pickles, ONNX files)
├── tests/
├── docs/
├── mkdocs.yml
├── pyproject.toml
├── docker-compose.yml
├── Dockerfile
└── dev.sh
```

---

## Layer rules

- `domain/` has no imports from `services/`, `adapters/`, or `infra/`
- `services/` has no imports from `adapters/`
- `infra/` is the only layer that imports storage SDKs (`asyncpg`, `arq`, `boto3`)
- `adapters/http/` is the only layer that imports FastAPI/Pydantic
