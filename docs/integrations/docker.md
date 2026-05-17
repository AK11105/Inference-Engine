# Docker

## Full stack (recommended)

Run Postgres, Redis, the API server, and the arq worker — all in containers:

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` builds the `inference-engine` image and starts all services via Docker Compose. See [Docker Compose](docker-compose.md) for a full breakdown of services, volumes, and profiles.

---

## Dockerfile

The project ships a two-stage `Dockerfile`:

1. **builder** — installs Python dependencies into `.venv` via `uv sync --frozen --no-dev`
2. **runtime** — copies `.venv` and `app/` into a clean `python:3.12-slim` image under a non-root `appuser`

Build and run standalone (falls back to SQLite + in-process async — no Postgres/Redis needed):

```bash
docker build -t inference-engine .
docker run -p 8000:8000 \
  -e API_KEYS="key1:tenant_a:predict,read_models" \
  -e ENV=production \
  inference-engine
```

---

## Services and ports

| Service | Host port |
|---|---|
| API server | `8000` |
| Postgres | `15432` |
| Redis | `6379` |

---

## Observability stack

```bash
bash dev.sh --observability
```

Starts Prometheus (`9090`) and Grafana (`3000`) alongside the core services. To add observability to an already-running stack:

```bash
docker compose --profile observability up -d
```

---

See [Docker Compose](docker-compose.md) for the full reference.
