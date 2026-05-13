# Docker

## Development (docker-compose)

```bash
cp .env.example .env
bash dev.sh
```

`dev.sh` starts Postgres and Redis via Docker Compose, runs the DB migration, launches the arq worker, and starts uvicorn.

---

## Dockerfile

The project includes a `Dockerfile` for building a production image:

```bash
docker build -t inference-engine .
docker run -p 8000:8000 \
  -e API_KEYS="key1:tenant_a:predict,read_models" \
  -e ENV=production \
  inference-engine
```

---

## docker-compose.yml

The included `docker-compose.yml` starts Postgres and Redis:

```bash
docker compose up -d
```

Services:

| Service | Port |
|---|---|
| Postgres | `5432` |
| Redis | `6379` |

---

## Linux / macOS

Edit `dev.sh` and change `VENV=".venv/Scripts"` to `VENV=".venv/bin"`.
