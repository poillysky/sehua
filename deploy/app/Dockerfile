# backend API + admin SPA 合一镜像
# 构建（仓库根目录）:
#   docker build -f deploy/app/Dockerfile -t poillysky/sehuatang-app:latest .
#
# 容器内:
#   nginx :80  → 静态管理端 + 反代 API
#   uvicorn 127.0.0.1:8080
#
# 日志:
#   LOG_LEVEL / UVICORN_LOG_LEVEL 控制 Python（默认 INFO，可 DEBUG）
#   nginx access/error → stdout/stderr（带 upstream 耗时）

# ---------- admin 前端 ----------
ARG NODE_IMAGE=node:22-bookworm-slim
FROM ${NODE_IMAGE} AS admin-build
WORKDIR /admin
COPY frontend/admin/package.json frontend/admin/package-lock.json ./
RUN npm install --no-audit --no-fund
COPY frontend/admin/ ./
RUN npx vite build && test -d dist

# ---------- runtime：backend + nginx ----------
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    LOG_LEVEL=INFO \
    UVICORN_LOG_LEVEL=info \
    TZ=Asia/Shanghai

ARG TARGETARCH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget ca-certificates curl gnupg p7zip-full nginx \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         | gpg --dearmor -o /usr/share/keyrings/postgresql-pgdg.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql-pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
         > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && set -eu; \
       case "${TARGETARCH}" in \
         amd64) RAR_ARCH=x64 ;; \
         arm64) RAR_ARCH=arm ;; \
         *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
       esac; \
       wget -q "https://www.rarlab.com/rar/rarlinux-${RAR_ARCH}-700.tar.gz" -O /tmp/rar.tar.gz; \
       tar -xzf /tmp/rar.tar.gz -C /tmp; \
       install -m 755 /tmp/rar/unrar /usr/local/bin/unrar; \
       rm -rf /tmp/rar /tmp/rar.tar.gz \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY backend/ .
COPY database /database

COPY --from=admin-build /admin/dist /usr/share/nginx/html
COPY deploy/app/nginx.conf /etc/nginx/nginx.conf
COPY deploy/app/default.conf /etc/nginx/conf.d/default.conf
COPY deploy/app/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/data/uploads/previews /var/log/nginx /var/cache/nginx \
    && nginx -t

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1/health || exit 1

CMD ["/entrypoint.sh"]
