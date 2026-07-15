# sehua

色花堂资源：**采集后端 + 管理前端 + 搜索前端**，共享 PostgreSQL；生产目标为家庭 NAS 全栈 Docker 部署。

## 结构

| 目录 | 说明 | 端口 |
|------|------|------|
| `backend/` | FastAPI 收集器（爬虫 / 入库 / 管理 API） | 8080 |
| `frontend/admin/` | 管理后台（Vite + React） | 8081 |
| `next-web/` | 搜索前端（Next.js） | 3010 |
| `database/migrations/` | PostgreSQL 迁移 | 5433 |
| `deploy/` | NAS Compose（只 pull 镜像） | — |
| `docs/` | [架构](docs/架构.md) · [设计说明](docs/设计说明.md) · [部署](docs/部署.md) |

本地开发可双击根目录 `start.bat`（后端 + 管理端 + 搜索端）。

## NAS 一键部署

镜像由 Actions 推到 GHCR：

- `ghcr.io/poillysky/sehuatang-backend`
- `ghcr.io/poillysky/sehuatang-admin`
- `ghcr.io/poillysky/sehuatang-search`

在 NAS 上：

```bash
cd deploy
# 按需改 docker-compose.nas.yml 中的密码、卷路径
docker login ghcr.io
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
# 或: ./update.sh
```

访问：搜索 `http://NAS_IP:3010` · 管理 `http://NAS_IP:8081` · API `http://NAS_IP:8080/health`

详情见 [docs/部署.md](docs/部署.md)。

## 说明

- `ed2k/` 为本地参考工程，**不入库**。
- 默认管理账号见 Compose 中 `INITIAL_ADMIN_*`，上线后请立刻修改。
