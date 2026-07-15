# NAS 部署

全栈四容器：**postgres + backend + admin + search**。镜像由 GitHub Actions 推到 GHCR，NAS 只 pull。

详细说明见 [docs/部署.md](../docs/部署.md)。

## 持久化目录

| 宿主机 | 容器 | 内容 |
|--------|------|------|
| `data/postgres` | postgres `/var/lib/postgresql/data` | 数据库 |
| `data/backend` | backend `/app/data` | cookies、预览图 |
| `data/search` | search `/app/data` | **115 配置** `p115-config.json` |
| `data/search-cache` | search `/app/.next/cache` | Next 缓存（可清空） |

admin 无状态，不挂卷。**不要**把 `/app/.next` 整目录或 `/app/public` 挂出去，会盖掉镜像内构建产物。

## 首次启动

```bash
cp .env.example .env
# 编辑 .env：GHCR_OWNER、密码、代理等

docker login ghcr.io
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

## 一键更新

```bash
chmod +x update.sh
./update.sh
```

## 访问

| 服务 | 地址 |
|------|------|
| 搜索 | http://NAS_IP:3008 |
| 管理 | http://NAS_IP:8081 |
| API | http://NAS_IP:8080/health |

管理账号来自 `.env` 的 `INITIAL_ADMIN_*`（首次启动写入库；之后改库内密码）。

## 本机构建试跑（可选）

```bash
# 在仓库根目录
docker build -f backend/Dockerfile -t sehuatang-backend .
docker build -t sehuatang-admin ./frontend/admin
docker build -t sehuatang-search ./next-web
```
