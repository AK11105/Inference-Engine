# Docker Compose

The project ships a production-ready `docker-compose.yml` and a dev-only `docker-compose.override.yml`. Together they cover the full stack: Postgres, Redis, the API server, the arq worker, and an optional Prometheus + Grafana observability stack.

---

## Services

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `postgres:16` | `15432` (host) → `5432` | Job store |
| `redis` | `redis:7-alpine` | `6379` | Async job queue + rate limiting |
| `api` | `inference-engine:latest` | `8000` | FastAPI inference server |
| `worker` | `inference-engine:latest` | — | arq background worker |
| `prometheus` *(optional)* | `prom/prometheus:v2.52.0` | `9090` | Metrics scraping |
| `grafana` *(optional)* | `grafana/grafana:10.4.2` | `3000` | Metrics dashboards |

`api` and `worker` share the same image. The worker is started with a different command (`arq app.infra.queue.worker.WorkerSettings`).

---

## Volumes

| Volume | Mounted at | Purpose |
|---|---|---|
| `pgdata` | `/var/lib/postgresql/data` | Postgres data persistence |
| `models` | `/app/models` | Shared model artifact storage between `api` and `worker` |
| `grafana_data` | `/var/lib/grafana` | Grafana dashboard persistence |

The `models` volume is the key shared resource. Both `api` and `worker` initialise their own `ModelRegistry` pointing at `/app/models`. Any artifact deployed via the CLI must be placed in this volume.

---

## Startup order

```
postgres (healthy) ──┐
                     ├──► api (healthy) ──► worker
redis    (healthy) ──┘
```

`api` waits for both Postgres and Redis to pass their healthchecks before starting. `worker` waits for `api` to pass its `/health` healthcheck. This ensures the model registry is warm before the worker begins processing jobs.

---

## Quick start

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` builds the `api` image and starts all services detached. Logs:

```bash
docker compose logs -f api worker
```

Stop everything:

```bash
docker compose down
```

Destroy volumes too (wipes Postgres data and models):

```bash
docker compose down -v
```

---

## Dev overrides (`docker-compose.override.yml`)

Docker Compose automatically merges `docker-compose.override.yml` when you run `docker compose up`. The override:

- Bind-mounts `./app` into `/app/app` — source changes are reflected immediately without rebuilding.
- Starts uvicorn with `--reload` so the server restarts on file saves.
- Sets `ENV=development` so the server starts without `API_KEYS`.

The override uses `build.target: builder` to skip the final `COPY app/` layer — the bind-mount provides the source instead.

> **Warning**
    The override is for local development only. Never use it in production — the bind-mount exposes your host source tree inside the container.

To run without the override (production-like locally):

```bash
docker compose -f docker-compose.yml up -d
```

---

## Observability stack

Prometheus and Grafana are gated behind the `observability` profile and do not start by default.

```bash
docker compose --profile observability up -d
```

| Service | URL | Credentials |
|---|---|---|
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | `admin` / `admin` |

Prometheus scrapes `/metrics` on the `api` service (no authentication required — `/metrics` is a public endpoint). Grafana is pre-provisioned with the Prometheus datasource from `deploy/grafana/provisioning/`.

---

## Environment variables

The `api` and `worker` services load `.env` via `env_file: .env` and then override two variables unconditionally:

```yaml
DATABASE_URL: postgresql://inference:inference@postgres:5432/inference_engine
REDIS_URL: redis://redis:6379/0
```

These use Docker's internal DNS (`postgres`, `redis`) — not `localhost`. If you run the API on the host while Postgres/Redis are in Docker, use the host-mapped ports instead:

```bash
DATABASE_URL=postgresql://inference:inference@127.0.0.1:15432/inference_engine
REDIS_URL=redis://127.0.0.1:6379/0
```

The `.env.example` file includes both variants as comments.

---

## Building the image manually

```bash
docker build -t inference-engine:latest .
```

The Dockerfile is a two-stage build:

1. **builder** — installs dependencies into `.venv` via `uv sync --frozen --no-dev`
2. **runtime** — copies `.venv` and `app/` into a clean `python:3.12-slim` image, creates a non-root `appuser`

The image exposes port `8000` and sets `MODELS_DIR=/app/models`.

Run standalone (no Postgres/Redis — falls back to SQLite + in-process async):

```bash
docker run -p 8000:8000 \
  -e API_KEYS="dev-key:tenant_dev:predict,read_models" \
  inference-engine:latest
```

---

## Healthcheck

The `api` container healthcheck uses Python's stdlib `urllib` to probe `GET /health`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

No extra dependencies required. The `worker` service waits for this healthcheck to pass before starting.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `api` container exits immediately | Check `docker compose logs api` — likely `API_KEYS` not set with `ENV=production` |
| `worker` stuck waiting for `api` | `api` healthcheck failing — check `docker compose logs api` |
| Postgres port conflict | Change `"15432:5432"` in `docker-compose.yml` if port 15432 is in use |
| Models not found in worker | Ensure both `api` and `worker` mount the same `models` volume |
| Source changes not reflected | Confirm `docker-compose.override.yml` is being loaded (`docker compose config` to verify) |
