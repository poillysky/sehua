# 本地构建，避免拉 Docker Hub 上的 libretranslate/libretranslate
ARG PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.11-slim-bookworm

FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    LT_HOST=0.0.0.0 \
    LT_PORT=5000 \
    LT_LOAD_ONLY=zh,en,ja,ko \
    LT_UPDATE_MODELS=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && pip install --no-cache-dir "libretranslate==1.6.5" \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 5000

CMD ["libretranslate"]
