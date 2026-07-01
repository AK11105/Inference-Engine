# Docker Quickstart

Run the full stack — Postgres, Redis, arq worker, and the API server — with a single command.

---

## Prerequisites

- Docker and Docker Compose (v2)

---

## Start everything

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` does the following:

1. Builds the `inference-engine` Docker image
2. Starts Postgres, Redis, the API server, and the arq worker via `docker compose up -d`

To also start the Prometheus + Grafana observability stack:

```bash
bash dev.sh --observability
```

---

## What's running

| Service | Address |
|---|---|
| API server | `http://localhost:8000` |
| Postgres | `localhost:15432` |
| Redis | `localhost:6379` |

With `--observability`:

| Service | Address | Credentials |
|---|---|---|
| Prometheus | `http://localhost:9090` | — |
| Grafana | `http://localhost:3000` | `admin` / `$GRAFANA_PASSWORD` (default: `admin`) |

Set `GRAFANA_PASSWORD` in `.env` to override the default password.

The **"Inference Engine"** Grafana dashboard is pre-provisioned — it appears in the Dashboards list automatically after startup with no manual import needed. Panels populate after the first scrape (~15 seconds).

---

## Verify

```bash
curl http://localhost:8000/health
# → {"status": "ok"}

curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: dev-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "echo", "version": "v1", "data": "hello"}'
# → {"result": "hello"}
```

---

## Logs and control

```bash
docker compose logs -f api worker   # follow logs
docker compose down                 # stop all services
docker compose down -v              # stop and delete volumes (wipes data)
```

---

## Environment

The `api` and `worker` containers load `.env` and override `DATABASE_URL` and `REDIS_URL` to use Docker's internal service names. You do not need to change these for local development.

To run the API on the host while Postgres/Redis are in Docker, use the host-mapped ports:

```bash
DATABASE_URL=postgresql://inference:inference@127.0.0.1:15432/inference_engine
REDIS_URL=redis://127.0.0.1:6379/0
```

---

See [Docker Compose](../integrations/docker-compose.md) for the full service reference, volumes, and observability stack.
