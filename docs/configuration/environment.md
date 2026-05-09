# Environment Variables

All configuration is via environment variables. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | hardcoded dev keys | Semicolon-separated `key:tenant_id:scope1,scope2` entries |
| `ENV` | *(unset)* | Set to `production` to enforce `API_KEYS` requirement at startup |
| `DATABASE_URL` | *(unset — SQLite)* | PostgreSQL DSN |
| `REDIS_URL` | *(unset — in-process)* | Redis DSN |
| `CPU_EXECUTOR_WORKERS` | `8` | Thread pool size for CPU executor |
| `GPU_EXECUTOR_WORKERS` | `2` | Thread pool size for GPU executor |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | *(unset — no export)* | OTLP/gRPC endpoint for distributed tracing |
| `OTEL_SERVICE_NAME` | `inference-engine` | Service name in traces |

---

## API_KEYS

```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

Scopes: `predict`, `read_models`, `admin`. See [Auth](../security/auth.md).

When unset, fallback dev keys are active (`dev-key`, `admin-key`). **Never use in production.**

---

## ENV

```
ENV=production
```

When set to `production`, the server refuses to start if `API_KEYS` is not set.

---

## DATABASE_URL

```
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/inference_engine
```

When set → `PostgresJobStore` (asyncpg-backed, non-blocking). Schema auto-created on first run via `PostgresJobStore.create_pool()`.  
When unset → `SQLiteJobStore` at `app/instance/jobs.db`.

If set but unreachable at startup, an `ERROR` is logged and the engine falls back to SQLite. This is not safe in production.

**Note:** Use `127.0.0.1` instead of `localhost` to avoid IPv6 resolution issues on Windows.

---

## REDIS_URL

```
REDIS_URL=redis://localhost:6379/0
```

When set → async jobs enqueued to arq; rate limits enforced across all processes.  
When unset → async jobs run as in-process async tasks; rate limits are per-process only (a warning is logged at startup).
