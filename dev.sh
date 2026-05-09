#!/usr/bin/env bash
# dev.sh — start postgres + redis, run DB migration, launch arq worker + uvicorn
set -euo pipefail

VENV=".venv/Scripts"          # Windows venv; change to .venv/bin on Linux/Mac
COMPOSE="docker compose"

# ── 1. Load env ─────────────────────────────────────────────────────────────
while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    export "$key=$value"
done < .env

# ── 2. Infra ────────────────────────────────────────────────────────────────
echo "==> Starting postgres + redis..."
$COMPOSE up -d postgres redis

echo "==> Waiting for postgres..."
until $COMPOSE exec -T postgres psql -U inference -d inference_engine -c "SELECT 1" -q > /dev/null 2>&1; do sleep 1; done

echo "==> Waiting for redis..."
until $COMPOSE exec -T redis redis-cli ping | grep -q PONG; do sleep 1; done

echo "RAW DATABASE_URL:"
printf '%q\n' "$DATABASE_URL"

# ── 3. DB migration ─────────────────────────────────────────────────────────
echo "==> Running DB migration..."
$VENV/python.exe -c "
import asyncio, os
from app.infra.jobs.postgres_job_store import PostgresJobStore
async def migrate():
    store = await PostgresJobStore.create_pool(dsn=os.environ['DATABASE_URL'])
    await store.close()
    print('Migration done.')
asyncio.run(migrate())
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
