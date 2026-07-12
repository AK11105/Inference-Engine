# Docker Compose — Internal Reference

How the compose setup works mechanically. Read this before adding or modifying any service.

---

## File structure

```
docker-compose.yml           # base — production-equivalent config
docker-compose.override.yml  # dev overrides — auto-merged by Docker Compose
dev.sh                       # bootstrap script for local development
```

---

## How the override merge works

Docker Compose automatically merges `docker-compose.override.yml` into `docker-compose.yml` whenever you run `docker compose up` (or `docker compose build`, `docker compose run`, etc.) from the project root. You do not pass any flag — it happens by convention.

The merge is **additive and overriding**:
- Keys that exist in the override replace the same key in the base
- Keys that don't exist in the override are inherited from the base unchanged
- Lists (like `volumes`, `environment`) are **appended**, not replaced

Example — what `api` actually looks like after merge when running `docker compose up`:

```yaml
# Effective config (base + override merged)
api:
  build: .
  image: inference-engine:latest
  command:                        # ← from override, replaces base CMD
    - uvicorn
    - app.adapters.http.app:app
    - --host
    - "0.0.0.0"
    - --port
    - "8000"
    - --reload                    # ← hot-reload added by override
  environment:
    DATABASE_URL: postgresql://...
    REDIS_URL: redis://...
    ENV: development              # ← added by override
  volumes:
    - ./models:/app/models        # ← from base (bind-mount, so CLI-deployed models are visible in-container)
    - ./app:/app/app              # ← added by override (source bind-mount)
```

**To run without the override** (production-like, no hot-reload, no source bind-mount):
```bash
docker compose -f docker-compose.yml up -d
```

---

## dev.sh vs docker compose directly

`dev.sh` does three things:
1. Detects whether `docker compose` (v2) or `docker-compose` (v1 standalone) is available
2. Copies `.env.example` → `.env` if `.env` doesn't exist
3. Runs `docker compose build api` then `docker compose up -d`

Because it runs plain `docker compose up`, the override is auto-loaded. **`dev.sh` always runs in dev mode.**

Running `docker compose -f docker-compose.yml up -d` directly skips the override — that is the production-equivalent local run.

---

## Profiles — how the observability stack works

Services tagged with `profiles: [observability]` (`prometheus`, `grafana`) are **excluded from all compose commands by default**. They only start when you explicitly pass `--profile observability`.

```bash
# Does NOT start prometheus or grafana:
docker compose up -d

# Starts everything including prometheus and grafana:
docker compose --profile observability up -d
```

**Rule for adding new services:** If a service is optional (not required for the app to function), give it a profile. If it is required, add it without a profile and add it to the startup dependency chain.

---

## Startup dependency chain

```
postgres (healthy) ──┐
                     ├──► api (healthy) ──► worker
redis    (healthy) ──┘
```

This is enforced via `depends_on` with `condition: service_healthy`. Each service must pass its healthcheck before the next one starts.

| Service | Healthcheck | What it checks |
|---|---|---|
| `postgres` | `pg_isready -U inference -d inference_engine` | Postgres accepting connections |
| `redis` | `redis-cli ping` | Redis responding |
| `api` | `GET /health` via Python urllib (see note below) | FastAPI app started and model registry warm |
| `worker` | none (see open issue) | — |

**Why worker waits for api:** The worker initialises its own `ModelRegistry` pointing at `/app/models`. Waiting for `api` to be healthy ensures the bind-mounted models directory is populated and the DB schema is migrated before the worker starts processing jobs.

**Note on api healthcheck:** Currently uses `python -c "import urllib.request; ..."` — fragile, being replaced with `curl` (tracked in compose hardening issue).

---

## Environment variable precedence

For `api` and `worker`, variables are resolved in this order (last wins):

1. `env_file: .env` — all variables from the `.env` file
2. `environment:` block in `docker-compose.yml` — `DATABASE_URL` and `REDIS_URL` are hardcoded here to use Docker internal DNS (`postgres`, `redis`)
3. `environment:` block in `docker-compose.override.yml` — `ENV: development` is added here

The hardcoded `DATABASE_URL` and `REDIS_URL` in the base compose file intentionally override whatever is in `.env` for those two keys. This ensures the containers always talk to each other via Docker's internal network, not via host-mapped ports.

If you run the API on the host (not in Docker), use the host-mapped ports from `.env`:
```bash
DATABASE_URL=postgresql://inference:inference@127.0.0.1:15432/inference_engine
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## Adding a new service — checklist

- [ ] Does it need to start by default? If not, add `profiles: [<name>]`
- [ ] Does it need to wait for another service? Add `depends_on` with `condition: service_healthy`
- [ ] Does it need a healthcheck? Add one — services without healthchecks cannot be depended on with `condition: service_healthy`
- [ ] Does it need persistent storage? Add a named volume and declare it in the top-level `volumes:` block
- [ ] Does it need env vars? Add to `.env.example` with a comment, not hardcoded in compose
