#!/usr/bin/env bash
# =============================================================================
# start.sh — One-command project startup
# Run from project root: bash scripts/start.sh
# =============================================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# ── 1. Check prerequisites ───────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || { echo "ERROR: Docker not installed"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "ERROR: Docker Compose not installed"; exit 1; }

# ── 2. Copy .env if missing ──────────────────────────────────────────────────
if [ ! -f .env ]; then
  echo "Creating .env from .env.example ..."
  cp .env.example .env
  echo "IMPORTANT: Edit .env and set your SECRET_KEY and SMTP credentials"
fi

# ── 3. Start all services ────────────────────────────────────────────────────
echo "Starting all services ..."
docker compose -f docker/docker-compose.yml up -d --build

# ── 4. Wait for backend to be healthy ────────────────────────────────────────
echo "Waiting for backend to be healthy ..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "Backend is up!"
    break
  fi
  echo "  attempt $i/30 ..."
  sleep 5
done

echo ""
echo "============================================================"
echo "  Job Application System is running!"
echo "  Frontend:  http://localhost:3000"
echo "  API docs:  http://localhost:8000/docs"
echo "  Health:    http://localhost:8000/health"
echo "============================================================"
echo ""
echo "First time setup:"
echo "  1. Open http://localhost:3000/register"
echo "  2. Create your account"
echo "  3. Upload your resume PDF in Settings"
echo "  4. Click 'Run Now' to start the agent pipeline"
echo ""