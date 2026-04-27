#!/usr/bin/env bash
# dev.sh — start postgres + redis, run DB migration, launch arq worker + uvicorn
set -euo pipefail

VENV=".venv/Scripts"          # Windows venv; change to .venv/bin on Linux/Mac
COMPOSE="docker compose"

# ── 1. Infra ────────────────────────────────────────────────────────────────
echo "==> Starting postgres + redis..."
$COMPOSE up -d postgres redis

echo "==> Waiting for postgres..."
until $COMPOSE exec -T postgres pg_isready -U inference -q; do sleep 1; done

echo "==> Waiting for redis..."
until $COMPOSE exec -T redis redis-cli ping | grep -q PONG; do sleep 1; done

# ── 2. Load env ─────────────────────────────────────────────────────────────
while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key=$value"
done < .env

# ── 3. DB migration ─────────────────────────────────────────────────────────
echo "==> Running DB migration..."
$VENV/python.exe -c "
from app.infra.jobs.postgres_job_store import PostgresJobStore
import os
PostgresJobStore(dsn=os.environ['DATABASE_URL'])
print('Migration done.')
"

# ── 4. arq worker ───────────────────────────────────────────────────────────
echo "==> Starting arq worker..."
$VENV/arq.exe app.infra.queue.worker.WorkerSettings &
ARQ_PID=$!

# ── 5. uvicorn ──────────────────────────────────────────────────────────────
echo "==> Starting uvicorn on :8000..."
$VENV/uvicorn.exe app.adapters.http.app:app --host 0.0.0.0 --port 8000 --reload &
UVICORN_PID=$!

# ── 6. Cleanup on exit ──────────────────────────────────────────────────────
trap 'echo "Stopping..."; kill $ARQ_PID $UVICORN_PID 2>/dev/null; $COMPOSE stop' EXIT INT TERM

echo ""
echo "Ready. Run:  bash tests/curl_test.sh http://localhost:8000"
echo "Press Ctrl+C to stop everything."
wait
