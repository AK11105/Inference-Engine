# Docker Quickstart

Run the full stack — Postgres, Redis, arq worker, and the API server — with a single command.

---

## Prerequisites

- Docker and Docker Compose
- Python 3.12+ with uv or pip

---

## Start everything

![Docker dev.sh startup sequence diagram](../assets/server-startup-light.png#only-light)
![Docker dev.sh startup sequence diagram](../assets/server-startup-dark.png#only-dark)

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` does the following in order:

1. Starts Postgres and Redis via Docker Compose
2. Waits for both services to be healthy
3. Runs the database schema migration
4. Launches the arq worker in the background
5. Starts uvicorn

---

## What's running

| Service | Address |
|---|---|
| API server | `http://localhost:8000` |
| Postgres | `localhost:5432` |
| Redis | `localhost:6379` |

---

## Environment

Edit `.env` to configure:

```bash
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/inference_engine
REDIS_URL=redis://localhost:6379/0
```

!!! note
    On Windows, use `127.0.0.1` instead of `localhost` in `DATABASE_URL` to avoid IPv6 resolution issues.

---

## Linux / macOS note

Edit the top of `dev.sh` and change `VENV=".venv/Scripts"` to `VENV=".venv/bin"`.

---

See [Docker Integration](../integrations/docker.md) for production Docker setup.
