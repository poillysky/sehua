#!/bin/sh
# 仅更新搜索端（与主栈 update.sh 分开）
set -e
cd "$(dirname "$0")"

echo "[1/3] pull search..."
docker compose -f docker-compose.search.yml pull

echo "[2/3] up search (remove orphan scrape container if any)..."
docker compose -f docker-compose.search.yml up -d --remove-orphans

echo "[3/3] prune dangling images..."
docker image prune -f

echo "OK $(date)"
docker compose -f docker-compose.search.yml ps
