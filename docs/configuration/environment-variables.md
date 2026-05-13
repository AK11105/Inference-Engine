# Environment Variables

All configuration is via environment variables. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | hardcoded dev keys | Semicolon-separated `key:tenant_id:scope1,scope2` entries |
| `ENV` | *(unset)* | Set to `production` to enforce `API_KEYS` at startup |
| `DATABASE_URL` | *(unset — SQLite)* | PostgreSQL DSN |
| `REDIS_URL` | *(unset — in-process)* | Redis DSN |
| `CPU_EXECUTOR_WORKERS` | `8` | Thread pool size for CPU executor |
| `GPU_EXECUTOR_WORKERS` | `2` | Thread pool size for GPU executor |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset)* | OTLP/gRPC endpoint for distributed tracing |
| `OTEL_SERVICE_NAME` | `inference-engine` | Service name in traces |

---

## API_KEYS

```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

Format: `key:tenant_id:scope1,scope2`. Entries separated by `;`. Scopes: `predict`, `read_models`, `admin`.

When unset, fallback dev keys are active (`dev-key`, `admin-key`).

!!! warning
    Never use dev keys in production. When `ENV=production`, the server refuses to start if `API_KEYS` is not set.

---

## DATABASE_URL

```
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/inference_engine
```

When set → `PostgresJobStore` (asyncpg-backed). Schema auto-created on first run.
When unset → `SQLiteJobStore` at `app/instance/jobs.db`.

!!! note
    Use `127.0.0.1` instead of `localhost` on Windows to avoid IPv6 resolution issues.

---

## REDIS_URL

```
REDIS_URL=redis://localhost:6379/0
```

When set → async jobs enqueued to arq; rate limits enforced across all processes.
When unset → async jobs run as in-process tasks; rate limits are per-process only.

---

## OTEL_EXPORTER_OTLP_ENDPOINT

```
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

When set and `opentelemetry-sdk` is installed, spans are exported via OTLP/gRPC. Otherwise tracing is a no-op.
