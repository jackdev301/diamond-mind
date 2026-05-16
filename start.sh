#!/usr/bin/env bash
# Start Diamond Mind — backend + frontend, kill both on exit.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv
source .venv/bin/activate

echo "==> Initializing DB..."
python scripts/init_db.py

echo "==> Running pregame update (seeds teams, form windows, weather)..."
python scripts/run_pregame_update.py

echo "==> Generating daily report..."
python scripts/run_daily_report.py

echo "==> Starting backend on :8000 and frontend on :3000..."
uvicorn app.api.routes:app --port 8000 &
BACKEND_PID=$!

cd frontend && npm run dev &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

echo ""
echo "  Backend:  http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both."
wait
