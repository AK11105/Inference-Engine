#!/usr/bin/env bash
# dev.sh — build and start the full stack via Docker Compose
set -euo pipefail

# ── Parse flags ─────────────────────────────────────────────────────────────
OBSERVABILITY=0
for arg in "$@"; do
    [[ "$arg" == "--observability" ]] && OBSERVABILITY=1
done

# ── Detect compose command ───────────────────────────────────────────────────
if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "ERROR: docker compose not found." >&2
    exit 1
fi

# ── Ensure .env exists ───────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    echo "==> .env not found — copying from .env.example"
    cp .env.example .env
fi

# ── Build app image ──────────────────────────────────────────────────────────
echo "==> Building inference-engine image..."
$COMPOSE build api

# ── Start everything ─────────────────────────────────────────────────────────
if [[ "$OBSERVABILITY" == "1" ]]; then
    echo "==> Starting all services + observability stack (Prometheus, Grafana)..."
    $COMPOSE --profile observability up -d
else
    echo "==> Starting all services (postgres, redis, api, worker)..."
    $COMPOSE up -d
fi

echo ""
echo "Services:"
echo "  API server  → http://localhost:8000"
echo "  Postgres    → localhost:15432"
echo "  Redis       → localhost:6379"
echo ""
echo "Logs:  docker compose logs -f api worker"
echo "Stop:  docker compose down"
echo ""
echo "Observability stack (Prometheus + Grafana):"
echo "  bash dev.sh --observability"
