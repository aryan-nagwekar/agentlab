#!/usr/bin/env bash
# One-command local demo stack: collector (:8000) + dashboard (:5173).
# Seeds the demo pipeline on first boot (only when the project has no runs).
set -euo pipefail
cd "$(dirname "$0")/.."

VENV="${VENV:-.venv}"
if [ ! -x "$VENV/bin/python" ]; then
  echo "No virtualenv found — run 'make install' first." >&2
  exit 1
fi
if [ ! -d apps/web/node_modules ]; then
  echo "Web dependencies missing — run 'make install' first." >&2
  exit 1
fi

API_PID=""
cleanup() { [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▸ starting collector on :8000 (SQLite at apps/api/agentlab.db)"
(cd apps/api && exec "../../$VENV/bin/python" -m uvicorn app.main:app --port 8000 --log-level warning) &
API_PID=$!

for _ in $(seq 1 60); do
  curl -fsS -m 1 http://localhost:8000/api/health >/dev/null 2>&1 && break
  sleep 0.25
done

existing=$(curl -fsS "http://localhost:8000/api/projects/demo-project/runs" 2>/dev/null | head -c 3 || true)
if [ -z "$existing" ] || [ "$existing" = "[]" ]; then
  echo "▸ seeding demo pipeline (success / retry / failure)"
  "$VENV/bin/python" examples/basic_multi_agent/run_demo.py --fast
else
  echo "▸ demo data already present — skipping seed (run 'make demo' to add more runs)"
fi

echo "▸ dashboard → http://localhost:5173"
cd apps/web && npm run dev
