#!/bin/bash
# 同容器：scrape-web(:9209) + next-web(:3000)
set -euo pipefail

ts() { date '+%Y-%m-%d %H:%M:%S%z'; }
log() { echo "$(ts) [entrypoint] $*"; }

export NODE_ENV="${NODE_ENV:-production}"
export HOSTNAME="${HOSTNAME:-0.0.0.0}"
export PORT="${PORT:-3000}"
export SCRAPE_PORT="${SCRAPE_PORT:-9209}"
export COVERS_DIR="${COVERS_DIR:-/data/covers}"
export META_DIR="${META_DIR:-/data/meta}"
export SCRAPE_CONFIG_DIR="${SCRAPE_CONFIG_DIR:-/data/config}"
export SCRAPE_ORIGIN="${SCRAPE_ORIGIN:-http://127.0.0.1:${SCRAPE_PORT}}"

mkdir -p "${COVERS_DIR}" "${META_DIR}" "${SCRAPE_CONFIG_DIR}" /app/.next/cache /app/data

log "=== sehuatang-search starting (next+scrape) ==="
log "next=:${PORT} scrape=:${SCRAPE_PORT} SCRAPE_ORIGIN=${SCRAPE_ORIGIN}"
log "COVERS_DIR=${COVERS_DIR} META_DIR=${META_DIR} SCRAPE_CONFIG_DIR=${SCRAPE_CONFIG_DIR}"
log "POSTGRES_HOST=${POSTGRES_HOST:-} POSTGRES_DB=${POSTGRES_DB:-}"

SCRAPE_PID=""
NEXT_PID=""

shutdown() {
  log "signal — stopping (scrape=${SCRAPE_PID:-?} next=${NEXT_PID:-?})"
  if [ -n "${NEXT_PID}" ] && kill -0 "${NEXT_PID}" 2>/dev/null; then
    kill -TERM "${NEXT_PID}" 2>/dev/null || true
  fi
  if [ -n "${SCRAPE_PID}" ] && kill -0 "${SCRAPE_PID}" 2>/dev/null; then
    kill -TERM "${SCRAPE_PID}" 2>/dev/null || true
  fi
  wait || true
  log "shutdown complete"
  exit 0
}
trap shutdown SIGTERM SIGINT

log "starting scrape-web ..."
(
  cd /opt/scrape
  export PORT="${SCRAPE_PORT}"
  exec node dist/index.js
) &
SCRAPE_PID=$!
log "scrape pid=${SCRAPE_PID}"

ready=0
for i in $(seq 1 60); do
  if kill -0 "${SCRAPE_PID}" 2>/dev/null \
    && curl -fsS "http://127.0.0.1:${SCRAPE_PORT}/health" >/dev/null 2>&1; then
    ready=1
    log "scrape health OK after ${i}s"
    break
  fi
  if ! kill -0 "${SCRAPE_PID}" 2>/dev/null; then
    log "ERROR: scrape exited before ready"
    wait "${SCRAPE_PID}" || true
    exit 1
  fi
  sleep 1
done
if [ "${ready}" != "1" ]; then
  log "WARN: scrape health not ready in 60s — starting next anyway"
fi

log "starting next-web ..."
(
  cd /app
  exec node server.js
) &
NEXT_PID=$!
log "next pid=${NEXT_PID}"
log "=== sehuatang-search ready (next :${PORT} + scrape :${SCRAPE_PORT}) ==="

set +e
wait -n "${SCRAPE_PID}" "${NEXT_PID}"
code=$?
set -e
log "child exited wait_code=${code} — stopping sibling"
shutdown
