#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run from WSL root: wsl -u root -d Ubuntu-22.04 bash scripts/env/install_docker_wsl.sh <username>" >&2
  exit 2
fi

DOCKER_USER="${1:-${SUDO_USER:-}}"
if [[ -z "$DOCKER_USER" ]] && id zhang >/dev/null 2>&1; then
  DOCKER_USER="zhang"
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y docker.io

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
mkdir -p /etc/docker
cp "$PROJECT_ROOT/config/docker-daemon.json" /etc/docker/daemon.json

if [[ -n "$DOCKER_USER" ]]; then
  usermod -aG docker "$DOCKER_USER"
fi

systemctl enable --now docker
systemctl restart docker
docker version
docker run --rm hello-world

echo "Docker installed. Open a new WSL shell before using docker without root."

