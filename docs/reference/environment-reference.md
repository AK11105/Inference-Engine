# Environment Variable Reference

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | hardcoded dev keys | `key:tenant_id:scope1,scope2` entries, separated by `;` |
| `ENV` | *(unset)* | Set to `production` to enforce `API_KEYS` at startup |
| `DATABASE_URL` | *(unset — SQLite)* | PostgreSQL DSN |
| `REDIS_URL` | *(unset — in-process)* | Redis DSN |
| `CPU_EXECUTOR_WORKERS` | `8` | Thread pool size for CPU executor |
| `GPU_EXECUTOR_WORKERS` | `2` | Thread pool size for GPU executor |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | OTLP/gRPC endpoint for tracing |
| `OTEL_SERVICE_NAME` | `inference-engine` | Service name in traces |
| `GROQ_API_KEY` | *(unset)* | Groq API key — required for CLI |
| `INFERENCE_ENGINE_LLM_MODEL` | `llama-3.3-70b-versatile` | LLM model override for CLI |
