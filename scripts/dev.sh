#!/usr/bin/env bash
# =============================================================================
# dev.sh — Run backend + frontend locally (without Docker)
# Requires: PostgreSQL, Redis, ChromaDB, Ollama running locally
# Run: bash scripts/dev.sh
# =============================================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Backend ───────────────────────────────────────────────────────────────────
echo "Starting FastAPI backend ..."
cd "$ROOT/backend"

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment ..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  playwright install chromium
else
  source .venv/bin/activate
fi

# Run backend in background
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# ── Frontend ──────────────────────────────────────────────────────────────────
echo "Starting React frontend ..."
cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "Installing npm dependencies ..."
  npm install
fi

npm run dev &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "Running:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait