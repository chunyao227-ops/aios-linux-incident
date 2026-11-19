#!/usr/bin/env bash
set -euo pipefail

ENV_DIR="${1:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3.10}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python 3.10 is required but ${PYTHON_BIN} was not found." >&2
  exit 2
fi

if [[ ! -d "${ENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${ENV_DIR}"
fi

source "${ENV_DIR}/bin/activate"
python --version
python -m pip install --upgrade pip

echo "Python 3.10 environment ready: ${ENV_DIR}"
echo "Next: install AIOS and Cerebrum according to the locked baseline."

