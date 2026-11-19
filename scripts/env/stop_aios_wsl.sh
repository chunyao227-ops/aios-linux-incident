#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${AIOS_STATE_DIR:-$HOME/.cache/aios}"
PID_FILE="$STATE_DIR/kernel.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$PID_FILE"
fi

pkill -f "uvicorn runtime.launch:app" 2>/dev/null || true
echo "AIOS kernel stopped"

