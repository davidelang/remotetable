#!/usr/bin/env bash
# Stop local EtherCalc smoke container.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
NAME="${REMOTETABLE_ETHERCALC_CONTAINER:-remotetable-ethercalc-smoke}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  docker compose -f "$DIR/docker-compose.yml" down 2>/dev/null || true
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose -f "$DIR/docker-compose.yml" down 2>/dev/null || true
fi
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null
  echo "OK removed container $NAME"
else
  echo "OK no container $NAME (already stopped)"
fi
