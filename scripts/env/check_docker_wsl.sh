#!/usr/bin/env bash
set -euo pipefail

docker version
docker info --format 'server={{.ServerVersion}} driver={{.Driver}} cgroup={{.CgroupDriver}}'
docker info --format '{{json .RegistryConfig.Mirrors}}'
docker run --rm hello-world

