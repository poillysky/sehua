# next-web + scrape-web 合一镜像
# 构建（仓库根目录）:
#   docker build -f deploy/search/Dockerfile -t poillysky/sehuatang-search:latest .
#
# 容器内:
#   next-web  :3000
#   scrape-web :9209（本机回环，SCRAPE_ORIGIN 默认 http://127.0.0.1:9209）

ARG NODE_IMAGE=node:20-bookworm-slim

# ---------- scrape-web ----------
FROM ${NODE_IMAGE} AS scrape-deps
WORKDIR /scrape
ENV npm_config_registry=https://registry.npmjs.org/
COPY scrape-web/package.json scrape-web/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM ${NODE_IMAGE} AS scrape-build
WORKDIR /scrape
ENV npm_config_registry=https://registry.npmjs.org/
COPY scrape-web/package.json scrape-web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY scrape-web/tsconfig.json ./
COPY scrape-web/src ./src
RUN npm run build && test -f dist/index.js

# ---------- next-web ----------
FROM ${NODE_IMAGE} AS next-deps
WORKDIR /next
ENV npm_config_registry=https://registry.npmjs.org/ \
    npm_config_fetch_timeout=600000 \
    npm_config_fetch_retries=5
COPY next-web/package.json next-web/package-lock.json ./
RUN npm ci --no-audit --no-fund --legacy-peer-deps

FROM ${NODE_IMAGE} AS next-build
WORKDIR /next
ENV BUILD_MODE=standalone \
    DOCKER_BUILD=1 \
    NODE_OPTIONS="--max-old-space-size=4096" \
    npm_config_registry=https://registry.npmjs.org/
COPY --from=next-deps /next/node_modules ./node_modules
COPY next-web/ ./
RUN node -e "console.log('next', require('next/package.json').version)" \
    && NODE_ENV=production node node_modules/next/dist/bin/next build \
    && test -f .next/standalone/server.js \
    && test -d .next/static

# ---------- runtime ----------
FROM ${NODE_IMAGE}
WORKDIR /app

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    SCRAPE_PORT=9209 \
    COVERS_DIR=/data/covers \
    META_DIR=/data/meta \
    SCRAPE_CONFIG_DIR=/data/config \
    SCRAPE_ORIGIN=http://127.0.0.1:9209 \
    TZ=Asia/Shanghai \
    NODE_OPTIONS="--dns-result-order=ipv4first"

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl bash \
    && rm -rf /var/lib/apt/lists/*

COPY --from=next-build /next/public ./public
COPY --from=next-build /next/.next/standalone ./
COPY --from=next-build /next/.next/static ./.next/static

COPY --from=scrape-deps /scrape/node_modules /opt/scrape/node_modules
COPY --from=scrape-build /scrape/dist /opt/scrape/dist
COPY scrape-web/package.json /opt/scrape/package.json

COPY deploy/search/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p .next/cache data /data/covers /data/meta

EXPOSE 3000 9209

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9209/health >/dev/null \
    && curl -fsS -o /dev/null http://127.0.0.1:3000/ \
    || exit 1

CMD ["/entrypoint.sh"]
