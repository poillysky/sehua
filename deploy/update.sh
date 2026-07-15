#!/bin/sh
# NAS 一键更新：拉取最新镜像并重启
set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "缺少 .env，请先: cp .env.example .env 并填写 GHCR_OWNER / 密码"
  exit 1
fi

echo "[1/3] pull..."
docker compose -f docker-compose.nas.yml pull

echo "[2/3] up..."
docker compose -f docker-compose.nas.yml up -d

echo "[3/3] prune dangling images..."
docker image prune -f

echo "OK $(date)"
docker compose -f docker-compose.nas.yml ps
