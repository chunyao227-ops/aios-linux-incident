#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
docker build -t "${SCENARIO_IMAGE:-aios-scenario-base:1.0}" "$ROOT_DIR/scenarios/common"
