#!/usr/bin/env bash
set -euo pipefail

OLLAMA_BIN="${OLLAMA_BIN:-$HOME/.local/bin/ollama}"
OLLAMA_HOST_VALUE="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_NUM_PARALLEL_VALUE="${OLLAMA_NUM_PARALLEL:-4}"
STATE_DIR="${OLLAMA_STATE_DIR:-$HOME/.cache/ollama}"
LOG_FILE="$STATE_DIR/serve.log"
PID_FILE="$STATE_DIR/serve.pid"

mkdir -p "$STATE_DIR"

if curl -fsS --max-time 2 "http://${OLLAMA_HOST_VALUE}/api/version" >/dev/null 2>&1; then
  curl -fsS "http://${OLLAMA_HOST_VALUE}/api/version"
  echo
  exit 0
fi

nohup env \
  OLLAMA_HOST="$OLLAMA_HOST_VALUE" \
  OLLAMA_NUM_PARALLEL="$OLLAMA_NUM_PARALLEL_VALUE" \
  OLLAMA_MAX_LOADED_MODELS=1 \
  "$OLLAMA_BIN" serve >>"$LOG_FILE" 2>&1 </dev/null &
echo "$!" >"$PID_FILE"

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://${OLLAMA_HOST_VALUE}/api/version"; then
    echo
    exit 0
  fi
  sleep 1
done

echo "Ollama server failed to start" >&2
tail -100 "$LOG_FILE" >&2
exit 1

