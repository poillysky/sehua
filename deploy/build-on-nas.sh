#!/bin/sh
# 在 NAS 上从源码构建镜像（不依赖 GitHub Actions / Hub pull）
#
# 推荐目录：
#   /vol1/1000/Docker/sehuatang/          ← compose + 本脚本
#   /vol1/1000/Docker/sehuatang/src/      ← 整仓源码
#
# 用法：
#   cd /vol1/1000/Docker/sehuatang
#   chmod +x build-on-nas.sh
#   ./build-on-nas.sh                  # 只构建主栈 app
#   ./build-on-nas.sh 1.2.0           # 指定标签
#   BUILD_SEARCH=1 ./build-on-nas.sh   # 额外构建 search
#   UP=1 ./build-on-nas.sh 1.2.0      # 构建后 compose up -d（不 pull）
#
set -eu
cd "$(dirname "$0")"
COMPOSE_DIR="$(pwd)"
SRC="${SRC_DIR:-$COMPOSE_DIR/src}"
TAG="${1:-}"

if [ ! -d "$SRC/backend" ] || [ ! -f "$SRC/deploy/app/Dockerfile" ]; then
  echo "找不到源码：$SRC/deploy/app/Dockerfile"
  echo "请把仓库完整复制到 $SRC （或设置 SRC_DIR=源码路径）"
  exit 1
fi

if [ -z "$TAG" ]; then
  if [ -f "$SRC/VERSION" ]; then
    TAG="$(tr -d ' \r\n' < "$SRC/VERSION")"
  else
    echo "请传入版本号，例如: ./build-on-nas.sh 1.2.0"
    exit 1
  fi
fi

echo "SRC=$SRC"
echo "TAG=$TAG"
echo "[app] sehua 主栈（backend+admin 合一）..."
docker build -f "$SRC/deploy/app/Dockerfile" \
  -t "poillysky/sehuatang-app:$TAG" \
  -t "poillysky/sehuatang-app:latest" \
  "$SRC"

if [ "${BUILD_SEARCH:-0}" = "1" ]; then
  echo "[search] next-web + scrape-web 合一镜像..."
  SEARCH_TAG="$TAG"
  if [ -f "$SRC/VERSION.search" ]; then
    SEARCH_TAG="$(tr -d ' \r\n' < "$SRC/VERSION.search")"
  fi
  NODE_IMAGE="${NODE_IMAGE:-}"
  if [ -n "$NODE_IMAGE" ]; then
    docker build -f "$SRC/deploy/search/Dockerfile" \
      --build-arg "NODE_IMAGE=$NODE_IMAGE" \
      -t "poillysky/sehuatang-search:$SEARCH_TAG" \
      -t "poillysky/sehuatang-search:latest" \
      "$SRC"
  else
    docker build -f "$SRC/deploy/search/Dockerfile" \
      -t "poillysky/sehuatang-search:$SEARCH_TAG" \
      -t "poillysky/sehuatang-search:latest" \
      "$SRC"
  fi
else
  echo "[search] 跳过（需要时: BUILD_SEARCH=1 ./build-on-nas.sh）"
fi

echo "构建完成："
docker images "poillysky/sehuatang-*" --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | head -20

if [ "${UP:-0}" = "1" ]; then
  echo "compose up 主栈（不 pull）..."
  docker compose -f docker-compose.nas.yml up -d --remove-orphans
  docker compose -f docker-compose.nas.yml ps
fi

echo "OK $(date) tag=$TAG"
