#!/bin/bash
# 同容器启动 uvicorn(API) + nginx(管理端)；日志详细且可 docker logs -f 直接看。
set -euo pipefail

LOG_LEVEL="${LOG_LEVEL:-INFO}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
UVICORN_HOST="${UVICORN_HOST:-127.0.0.1}"
UVICORN_PORT="${UVICORN_PORT:-8080}"

ts() { date '+%Y-%m-%d %H:%M:%S%z'; }
log() { echo "$(ts) [entrypoint] $*"; }

export LOG_LEVEL
export PYTHONUNBUFFERED=1

log "=== sehuatang-app starting ==="
log "LOG_LEVEL=${LOG_LEVEL} UVICORN_LOG_LEVEL=${UVICORN_LOG_LEVEL}"
log "listen nginx=:80  uvicorn=${UVICORN_HOST}:${UVICORN_PORT}"
log "TZ=${TZ:-} POSTGRES_HOST=${POSTGRES_HOST:-} POSTGRES_PORT=${POSTGRES_PORT:-} POSTGRES_DB=${POSTGRES_DB:-}"
log "AUTH_REQUIRED=${AUTH_REQUIRED:-} BACKUP_DIR=${BACKUP_DIR:-}"
log "SEARCH_FRONTEND_URL=${SEARCH_FRONTEND_URL:-} WEB_CRAWLER_PROXY=${WEB_CRAWLER_PROXY:-}"
log "cwd=$(pwd) python=$(command -v python3 || command -v python) nginx=$(command -v nginx)"

if [ ! -d /usr/share/nginx/html ] || [ -z "$(ls -A /usr/share/nginx/html 2>/dev/null || true)" ]; then
  log "WARN: admin static files missing under /usr/share/nginx/html"
else
  log "admin static: $(ls /usr/share/nginx/html | tr '\n' ' ')"
fi

log "nginx -t ..."
nginx -t
log "nginx config OK"

UV_PID=""
NG_PID=""

shutdown() {
  log "signal received — shutting down (uvicorn_pid=${UV_PID:-?} nginx_pid=${NG_PID:-?})"
  if [ -n "${NG_PID}" ] && kill -0 "${NG_PID}" 2>/dev/null; then
    kill -TERM "${NG_PID}" 2>/dev/null || true
  fi
  if [ -n "${UV_PID}" ] && kill -0 "${UV_PID}" 2>/dev/null; then
    kill -TERM "${UV_PID}" 2>/dev/null || true
  fi
  wait || true
  log "shutdown complete"
  exit 0
}
trap shutdown SIGTERM SIGINT

log "starting uvicorn ..."
python -m uvicorn api.main:app \
  --host "${UVICORN_HOST}" \
  --port "${UVICORN_PORT}" \
  --log-level "${UVICORN_LOG_LEVEL}" \
  --access-log \
  --proxy-headers \
  --forwarded-allow-ips='*' &
UV_PID=$!
log "uvicorn pid=${UV_PID}"

# 等 API 就绪再对外开 nginx，避免刚启动打 /api 502
ready=0
for i in $(seq 1 60); do
  if kill -0 "${UV_PID}" 2>/dev/null \
    && curl -fsS "http://${UVICORN_HOST}:${UVICORN_PORT}/health" >/dev/null 2>&1; then
    ready=1
    log "uvicorn health OK after ${i}s"
    break
  fi
  if ! kill -0 "${UV_PID}" 2>/dev/null; then
    log "ERROR: uvicorn exited before ready"
    wait "${UV_PID}" || true
    exit 1
  fi
  sleep 1
done
if [ "${ready}" != "1" ]; then
  log "WARN: uvicorn health not ready in 60s — starting nginx anyway"
fi

log "starting nginx (daemon off) ..."
nginx -g 'daemon off;' &
NG_PID=$!
log "nginx pid=${NG_PID}"
log "=== sehuatang-app ready (admin+api on :80) ==="

# 任一子进程退出则整容器退出，便于 restart: always 拉起
set +e
wait -n "${UV_PID}" "${NG_PID}"
code=$?
set -e
log "child exited wait_code=${code} — stopping sibling"
shutdown
