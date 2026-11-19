#!/usr/bin/env bash
set -euo pipefail

export MODEL_BASE_URL="${MODEL_BASE_URL:-http://127.0.0.1:11434/v1}"
export MODEL_NAME="${MODEL_NAME:-qwen2:7b-instruct}"
export MODEL_API_KEY="${MODEL_API_KEY:-}"
export MODEL_BACKEND="${MODEL_BACKEND:-ollama-local}"

cat <<EOF
MODEL_BASE_URL=${MODEL_BASE_URL}
MODEL_NAME=${MODEL_NAME}
MODEL_API_KEY=${MODEL_API_KEY:-<empty>}
MODEL_BACKEND=${MODEL_BACKEND}
EOF

