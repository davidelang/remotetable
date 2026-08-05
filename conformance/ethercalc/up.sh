#!/usr/bin/env bash
# Start local EtherCalc for remotetable smoke.
# Prefers `docker compose`; falls back to `docker-compose` or plain `docker run`.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
NAME="${REMOTETABLE_ETHERCALC_CONTAINER:-remotetable-ethercalc-smoke}"
IMAGE="${REMOTETABLE_ETHERCALC_IMAGE:-audreyt/ethercalc:latest}"
PORT="${REMOTETABLE_ETHERCALC_PORT:-8000}"
BASE="${REMOTETABLE_ETHERCALC_BASE_URL:-http://127.0.0.1:${PORT}}"
ROOM="${REMOTETABLE_ETHERCALC_ROOM:-ve-smoke}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found — install docker or skip ethercalc local smoke" >&2
  exit 1
fi

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$DIR/docker-compose.yml" "$@"
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "$DIR/docker-compose.yml" "$@"
    return
  fi
  return 1
}

echo "Starting EtherCalc ($IMAGE) on $BASE …"
if compose up -d 2>/dev/null; then
  echo "  via docker compose"
else
  # Plain docker run fallback (no compose plugin)
  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    docker start "$NAME" >/dev/null
    echo "  restarted container $NAME"
  else
    docker run -d --name "$NAME" -p "${PORT}:8000" "$IMAGE" >/dev/null
    echo "  docker run $NAME"
  fi
fi

echo "Waiting for health (GET $BASE/$ROOM.csv) …"
ok=0
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$BASE/$ROOM.csv" 2>/dev/null || echo 000)
  # 200 empty room or 404 until first write — both mean HTTP is up
  if [[ "$code" == "200" || "$code" == "404" || "$code" == "302" ]]; then
    ok=1
    break
  fi
  # also accept root
  code2=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$BASE/" 2>/dev/null || echo 000)
  if [[ "$code2" =~ ^[23] ]]; then
    ok=1
    break
  fi
  sleep 1
done
if [[ "$ok" -ne 1 ]]; then
  echo "WARNING: health check timed out — container may still be starting" >&2
  docker ps -a --filter "name=$NAME" || true
  exit 1
fi
echo "OK EtherCalc up"
echo "  base_url=$BASE"
echo "  room=$ROOM  (one room ≈ one tab for smoke)"
echo "  smoke: REMOTETABLE_ETHERCALC_LOCAL=1 python3 conformance/ethercalc_live_smoke.py"
echo "  stop:  conformance/ethercalc/down.sh"
