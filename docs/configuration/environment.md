# Environment Variables

All configuration is via environment variables. Copy `.env.example` to `.env`.

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | hardcoded dev keys | Semicolon-separated `key:tenant_id:scope1,scope2` entries |
| `DATABASE_URL` | *(unset — SQLite)* | PostgreSQL DSN |
| `REDIS_URL` | *(unset — in-process)* | Redis DSN |

---

## API_KEYS

```
API_KEYS=key1:tenant_a:predict,read_models;key2:tenant_b:predict,read_models,admin
```

Scopes: `predict`, `read_models`, `admin`. See [Auth](../security/auth.md).

When unset, fallback dev keys are active (`dev-key`, `admin-key`). **Never use in production.**

---

## DATABASE_URL

```
DATABASE_URL=postgresql://user:password@localhost:5432/inference_engine
```

When set → `PostgresJobStore`. Schema auto-created on first run.  
When unset → `SQLiteJobStore` at `app/instance/jobs.db`.

---

## REDIS_URL

```
REDIS_URL=redis://localhost:6379/0
```

When set → async jobs enqueued to arq; rate limits enforced across all processes.  
When unset → async jobs run in-process thread pool; rate limits are per-process only.
