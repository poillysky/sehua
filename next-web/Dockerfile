# GitHub Actions / 通用构建默认官方 Debian 镜像（glibc，jieba 原生包更稳）
# 国内本地若拉不动可: --build-arg NODE_IMAGE=docker.m.daocloud.io/library/node:20-bookworm-slim
ARG NODE_IMAGE=node:20-bookworm-slim

FROM ${NODE_IMAGE} AS base
WORKDIR /app
# CI 用官方源；覆盖仓库内 .npmrc 的 npmmirror，避免海外 runner 抽风
ENV npm_config_registry=https://registry.npmjs.org/ \
    npm_config_fetch_timeout=600000 \
    npm_config_fetch_retries=5

FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --legacy-peer-deps

FROM base AS builder
ENV BUILD_MODE=standalone \
    DOCKER_BUILD=1 \
    NODE_OPTIONS="--max-old-space-size=4096"

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN node -e "console.log('next', require('next/package.json').version)" \
    && NODE_ENV=production node node_modules/next/dist/bin/next build

FROM ${NODE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
RUN mkdir -p .next/cache data

EXPOSE 3000
ENV HOSTNAME=0.0.0.0 PORT=3000
CMD ["node", "server.js"]
