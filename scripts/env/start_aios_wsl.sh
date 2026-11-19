#!/usr/bin/env bash
set -euo pipefail

AIOS_ROOT="${AIOS_ROOT:-$HOME/AIOS}"
VENV_ROOT="${VENV_ROOT:-$HOME/venv-aios}"
AIOS_HOST="${AIOS_HOST:-127.0.0.1}"
AIOS_PORT="${AIOS_PORT:-8000}"
STATE_DIR="${AIOS_STATE_DIR:-$HOME/.cache/aios}"
LOG_FILE="$STATE_DIR/kernel.log"
PID_FILE="$STATE_DIR/kernel.pid"

mkdir -p "$STATE_DIR"

if curl -fsS --max-time 2 "http://${AIOS_HOST}:${AIOS_PORT}/status" >/dev/null 2>&1; then
  curl -fsS "http://${AIOS_HOST}:${AIOS_PORT}/status"
  echo
  exit 0
fi

source "$VENV_ROOT/bin/activate"
cd "$AIOS_ROOT"

nohup python -m uvicorn runtime.launch:app \
  --host "$AIOS_HOST" \
  --port "$AIOS_PORT" \
  >>"$LOG_FILE" 2>&1 </dev/null &
echo "$!" >"$PID_FILE"

for _ in $(seq 1 120); do
  if curl -fsS --max-time 2 "http://${AIOS_HOST}:${AIOS_PORT}/status"; then
    echo
    exit 0
  fi
  sleep 1
done

echo "AIOS kernel failed to start" >&2
tail -150 "$LOG_FILE" >&2
exit 1

