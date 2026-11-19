#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${OLLAMA_STATE_DIR:-$HOME/.cache/ollama}"
PID_FILE="$STATE_DIR/serve.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$PID_FILE"
fi

pkill -f "ollama serve" 2>/dev/null || true
echo "Ollama stopped"

