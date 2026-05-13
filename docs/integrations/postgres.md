# Postgres

Postgres is used as the job store when `DATABASE_URL` is set.

---

## Configuration

```bash
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/inference_engine
```

!!! note
    Use `127.0.0.1` instead of `localhost` on Windows to avoid IPv6 resolution issues.

---

## Start Postgres

```bash
docker compose up -d
```

Or run directly:

```bash
docker run -p 5432:5432 \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=inference_engine \
  postgres:16-alpine
```

---

## Schema

The `jobs` table is created automatically on first startup. Migrations are additive-only — columns are never dropped. Migration state is tracked in a `schema_migrations` table.

---

## Fallback behaviour

If `DATABASE_URL` is set but Postgres is unreachable at startup, the engine logs an `ERROR` and falls back to SQLite. This is not safe in production — ensure Postgres is healthy before starting the server.
