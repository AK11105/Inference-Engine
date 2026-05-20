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

## Network

All services share a single explicit bridge network: `inference-net`. Defining it explicitly (rather than relying on the auto-created default) ensures the network is fully registered before any container — including profile-gated ones like Prometheus — attempts to attach. This prevents the `network not found` race condition that can occur when the observability profile is started alongside the core stack.

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
bash dev.sh --observability
```

Or, to add observability to an already-running stack:

```bash
docker compose --profile observability up -d
```

| Service | URL | Credentials |
|---|---|---|
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | `admin` / `$GRAFANA_PASSWORD` (default: `admin`) |

Prometheus scrapes `/metrics` on the `api` service (no authentication required — `/metrics` is a public endpoint). Grafana is pre-provisioned with the Prometheus datasource from `deploy/grafana/provisioning/`.

---

## Environment variables

The `api` and `worker` services load `.env` via `env_file: .env` and then override two variables unconditionally:

```yaml
DATABASE_URL: postgresql://${POSTGRES_USER:-inference}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-inference_engine}
REDIS_URL: redis://:${REDIS_PASSWORD:-}@redis:6379/0   # empty password = no-auth; set REDIS_PASSWORD to enable requirepass
```

These use Docker's internal DNS (`postgres`, `redis`) — not `localhost`. If you run the API on the host while Postgres/Redis are in Docker, use the host-mapped ports instead:

```bash
DATABASE_URL=postgresql://inference:your-password@127.0.0.1:15432/inference_engine
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

The `api` container healthcheck uses `curl` to probe `GET /health`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -f http://localhost:8000/health || exit 1
```

`curl` is installed in the runtime image (`apt-get install -y --no-install-recommends curl`). The `worker` service waits for this healthcheck to pass before starting.

---

## Worker healthcheck

The `worker` service has no HTTP port, so its healthcheck performs a Redis ping — confirming the worker can reach its queue:

```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import redis,os; redis.from_url(os.environ['REDIS_URL']).ping()\""]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 20s
```

A crashed or hung worker that can no longer reach Redis will fail this check, allowing Docker and any orchestrator to restart it automatically.

---

## Worker resource limits

The worker has a 2 GB memory cap to prevent a runaway inference job from consuming all host memory and taking down other services:

```yaml
deploy:
  resources:
    limits:
      memory: 2g
```

Tune this value to match the largest model artifact you expect to load. The limit applies per worker replica.

---

## API resource limits

The `api` service has a memory limit controlled by `API_MEMORY_LIMIT` (default `4g`):

```yaml
deploy:
  resources:
    limits:
      memory: ${API_MEMORY_LIMIT:-4g}
```

Set `API_MEMORY_LIMIT` in `.env` to tune it for your largest loaded model. Without a limit, an OOM in the API container can exhaust host memory and take down all co-located services.

---

## Postgres credentials

Postgres credentials are read from environment variables — no defaults are baked into the compose file:

```yaml
POSTGRES_USER: ${POSTGRES_USER:-inference}
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
POSTGRES_DB: ${POSTGRES_DB:-inference_engine}
```

`POSTGRES_PASSWORD` uses the `:?` modifier: Compose will refuse to start if it is unset or empty. Set it in `.env`:

```bash
POSTGRES_PASSWORD=change-me-in-production
```

> **Warning**  
> Never commit a real password to `.env`. The `.env.example` ships with a placeholder value (`change-me-in-production`) as a reminder.

---

## Redis password

Redis authentication is optional and controlled by `REDIS_PASSWORD`. When set, the Redis container starts with `--requirepass` and the `REDIS_URL` passed to `api` and `worker` includes the credential automatically:

```bash
# .env
REDIS_PASSWORD=change-me-in-production
```

Leave `REDIS_PASSWORD` unset (or commented out) for no-auth Redis — acceptable for local development on a trusted network, but not for any shared or production deployment.

---

## Grafana admin password

The Grafana admin password is configurable via the `GRAFANA_PASSWORD` environment variable:

```yaml
environment:
  GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
```

The default is `admin` (suitable for local development). For any shared or production deployment, set `GRAFANA_PASSWORD` in `.env`:

```bash
GRAFANA_PASSWORD=change-me-in-production
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `api` container exits immediately | Check `docker compose logs api` — likely `API_KEYS` not set with `ENV=production` |
| `worker` stuck waiting for `api` | `api` healthcheck failing — check `docker compose logs api` |
| Postgres port conflict | Change `"15432:5432"` in `docker-compose.yml` if port 15432 is in use |
| Models not found in worker | Ensure both `api` and `worker` mount the same `models` volume |
| Source changes not reflected | Confirm `docker-compose.override.yml` is being loaded (`docker compose config` to verify) |
| `network not found` on Prometheus start | Run `docker compose down` then `bash dev.sh --observability` to let Compose create the named network before attaching profile services |
| `POSTGRES_PASSWORD must be set` on startup | Add `POSTGRES_PASSWORD=...` to your `.env` file — the compose file requires it explicitly |
| Redis `WRONGPASS` / auth errors | Set `REDIS_PASSWORD` in `.env` to match the value used when the Redis container was first started; or `docker compose down -v` to reset |
