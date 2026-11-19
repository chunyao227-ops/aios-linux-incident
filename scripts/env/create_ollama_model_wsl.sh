#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/model.gguf" >&2
  exit 2
fi

MODEL_PATH="$1"
MODEL_NAME="${MODEL_NAME:-qwen2:7b-instruct}"
OLLAMA_BIN="${OLLAMA_BIN:-$HOME/.local/bin/ollama}"
STATE_DIR="${OLLAMA_STATE_DIR:-$HOME/.cache/ollama}"
TEMPLATE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/config/ollama/Modelfile.qwen2-7b-instruct"
GENERATED_MODELFILE="$STATE_DIR/Modelfile.$MODEL_NAME"

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model file not found: $MODEL_PATH" >&2
  exit 2
fi

bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start_ollama_wsl.sh" >/dev/null

mkdir -p "$STATE_DIR"
sed "s|__MODEL_PATH__|$MODEL_PATH|g" "$TEMPLATE_FILE" >"$GENERATED_MODELFILE"

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}" \
  "$OLLAMA_BIN" create "$MODEL_NAME" -f "$GENERATED_MODELFILE"

OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}" "$OLLAMA_BIN" list

