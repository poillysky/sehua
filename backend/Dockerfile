# 构建上下文必须是仓库根目录:
#   docker build -f backend/Dockerfile -t sehuatang-backend .
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

ARG TARGETARCH
# Postgres 服务为 16.x；Debian bookworm 默认 postgresql-client 是 15，需 PGDG 的 16 客户端
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget ca-certificates curl gnupg p7zip-full \
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
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY backend/ .
# migrate.py: Path(__file__).parents[2]/database/migrations → /database/migrations
COPY database /database

RUN mkdir -p /app/data/uploads/previews

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
