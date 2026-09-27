#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  echo "Run ./setup_macos.sh first."
  exit 1
fi

cleanup() {
  echo
  echo "Stopping MediExplain+..."
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" "${OLLAMA_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Ollama may already be running (desktop app/service).
if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama already running."
  OLLAMA_PID=""
else
  echo "Starting Ollama..."
  ollama serve > /tmp/mediexplain_ollama.log 2>&1 &
  OLLAMA_PID=$!
  sleep 2
fi

echo "Starting backend..."
(
  cd backend
  source .venv/bin/activate
  exec uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

echo "Starting frontend..."
(
  cd frontend
  exec npm run dev -- --host 127.0.0.1
) &
FRONTEND_PID=$!

echo
echo "MediExplain+ is starting:"
echo "  App:     http://127.0.0.1:5173"
echo "  API:     http://127.0.0.1:8000"
echo "  API docs:http://127.0.0.1:8000/docs"
echo
echo "Press Ctrl+C to stop."
wait
