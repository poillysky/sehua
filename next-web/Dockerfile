# GitHub Actions 默认用官方镜像；国内可 --build-# GitHub Actions 用官方镜像；国内本地构建可: --build-arg NODE_IMAGE=docker.m.daocloud.io/library/node:20-alpine
ARG NODE_IMAGE=node:20-alpine
ARG NODE_IMAGE=node:20-alpine

FROM ${NODE_IMAGE} AS base
WORKDIR /app
ENV npm_config_registry=https://registry.npmmirror.com \
    npm_config_fetch_timeout=600000 \
    npm_config_fetch_retries=5

FROM base AS deps
COPY package.json package-lock.json .npmrc ./
RUN npm ci --no-audit --no-fund

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
RUN apk add --no-cache ca-certificates

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/.next/server ./.next/server
RUN mkdir -p .next/cache data

EXPOSE 3000
ENV HOSTNAME=0.0.0.0 PORT=3000
CMD ["node", "server.js"]
