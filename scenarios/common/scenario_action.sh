#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <scenario-id> <action>" >&2
  exit 2
fi

SCENARIO_ID="$1"
ACTION="$2"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_NAME="${SCENARIO_IMAGE:-aios-scenario-base:1.0}"
CONTAINER_NAME="aios-scenario-${SCENARIO_ID}"

build_image() {
  docker build -t "$IMAGE_NAME" "$ROOT_DIR/scenarios/common"
}

destroy_container() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}

start_container() {
  if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    build_image
  fi
  destroy_container
  local var_size="8m"
  if [[ "$SCENARIO_ID" == "f5" ]]; then
    var_size="16m"
  fi
  docker run -d \
    --name "$CONTAINER_NAME" \
    --network none \
    --read-only \
    --tmpfs "/etc/demo:rw,size=1m,mode=1777" \
    --tmpfs "/var/lib/demo:rw,size=${var_size},mode=1777" \
    --tmpfs "/run/demo:rw,size=1m,mode=1777" \
    --tmpfs "/tmp:rw,size=8m,mode=1777" \
    -e "SCENARIO_ID=$SCENARIO_ID" \
    "$IMAGE_NAME" >/dev/null
  docker exec "$CONTAINER_NAME" python /opt/demo/control.py wait
}

container_exec() {
  docker exec "$CONTAINER_NAME" python /opt/demo/control.py "$@"
}

case "$ACTION" in
  build)
    build_image
    ;;
  start|reset)
    start_container
    ;;
  inject)
    container_exec inject --scenario "$SCENARIO_ID"
    ;;
  repair)
    container_exec repair --scenario "$SCENARIO_ID"
    ;;
  verify)
    container_exec verify
    ;;
  pressure)
    container_exec pressure
    ;;
  hash)
    container_exec hash
    ;;
  destroy)
    destroy_container
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 2
    ;;
esac
