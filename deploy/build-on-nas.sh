#!/bin/sh
# 在 NAS 上从源码构建 1.0.x 镜像（不依赖 GitHub Actions / Hub pull）
#
# 推荐目录：
#   /vol1/1000/Docker/sehuatang/          ← compose + 本脚本
#   /vol1/1000/Docker/sehuatang/src/      ← 整仓源码（含 backend/ frontend/ next-web/ VERSION）
#
# 用法：
#   cd /vol1/1000/Docker/sehuatang
#   chmod +x build-on-nas.sh
#   ./build-on-nas.sh                  # 读 src/VERSION
#   ./build-on-nas.sh 1.0.19           # 指定标签
#   UP=1 ./build-on-nas.sh 1.0.19      # 构建后 compose up -d（不 pull）
#
set -eu
cd "$(dirname "$0")"
COMPOSE_DIR="$(pwd)"
SRC="${SRC_DIR:-$COMPOSE_DIR/src}"
TAG="${1:-}"

if [ ! -d "$SRC/backend" ] || [ ! -f "$SRC/backend/Dockerfile" ]; then
  echo "找不到源码：$SRC/backend"
  echo "请把仓库完整复制到 $SRC （或设置 SRC_DIR=源码路径）"
  exit 1
fi

if [ -z "$TAG" ]; then
  if [ -f "$SRC/VERSION" ]; then
    TAG="$(tr -d ' \r\n' < "$SRC/VERSION")"
  else
    echo "请传入版本号，例如: ./build-on-nas.sh 1.0.19"
    exit 1
  fi
fi

echo "SRC=$SRC"
echo "TAG=$TAG"
echo "[1/3] backend..."
docker build -f "$SRC/backend/Dockerfile" \
  -t "poillysky/sehuatang-backend:$TAG" \
  -t "poillysky/sehuatang-backend:latest" \
  "$SRC"

echo "[2/3] admin..."
docker build -f "$SRC/frontend/admin/Dockerfile" \
  -t "poillysky/sehuatang-admin:$TAG" \
  -t "poillysky/sehuatang-admin:latest" \
  "$SRC/frontend/admin"

echo "[3/3] search（较慢、吃内存）..."
# 国内拉不动官方 node 时可：
#   NODE_IMAGE=docker.m.daocloud.io/library/node:20-bookworm-slim ./build-on-nas.sh
NODE_IMAGE="${NODE_IMAGE:-}"
if [ -n "$NODE_IMAGE" ]; then
  docker build -f "$SRC/next-web/Dockerfile" \
    --build-arg "NODE_IMAGE=$NODE_IMAGE" \
    -t "poillysky/sehuatang-search:$TAG" \
    -t "poillysky/sehuatang-search:latest" \
    "$SRC/next-web"
else
  docker build -f "$SRC/next-web/Dockerfile" \
    -t "poillysky/sehuatang-search:$TAG" \
    -t "poillysky/sehuatang-search:latest" \
    "$SRC/next-web"
fi

echo "构建完成："
docker images "poillysky/sehuatang-*" --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | head -20

if [ "${UP:-0}" = "1" ]; then
  echo "compose up（不 pull）..."
  docker compose -f docker-compose.nas.yml up -d
  docker compose -f docker-compose.nas.yml ps
fi

echo "OK $(date) tag=$TAG"
