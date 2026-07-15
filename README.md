# sehua（sehuatang）

色花堂资源采集与检索：**采集后端 + 管理前端 + 搜索前端**，共享 PostgreSQL。  
生产目标为家庭 NAS **全栈 Docker**；镜像由 GitHub Actions 构建并推送到 **Docker Hub**（及 GHCR），NAS **只 pull、不本地 build**。

当前版本：**1.0.4**（见 [`VERSION`](./VERSION)）。发版按 `1.0.1` → `1.0.2` → `1.0.3` → `1.0.4` → … **递增叠加**，旧版本标签保留。

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 网站爬虫 | 按发帖时间序列表扫帖；每日首页捕新，当天后续轮次只深扫 |
| 资源入库 | 磁力 / EM 下载链入库；带来源论坛与板块元数据 |
| 管理后台 | 登录鉴权、爬虫拓扑、导入、资源核对、重爬 |
| 搜索前端 | Next.js 搜 / 看详情；可选 115 离线转存 + 云解压 |
| 数据库 | PostgreSQL 16，SQL 迁移在 `database/migrations/` |

不做：Telegram 监听、NAS 上编译业务镜像、管理端原生 App。

---

## 仓库结构

```text
sehuatang/
├── backend/                 # FastAPI：爬虫 / 入库 / 管理 API
├── frontend/admin/          # 管理端 Vite + React（Nginx 静态）
├── next-web/                # 搜索端 Next.js（GraphQL + 直连 PG）
├── database/migrations/     # PostgreSQL 迁移
├── deploy/                  # NAS Compose（只 pull）
│   ├── docker-compose.nas.yml
│   └── update.sh
├── docs/                    # 架构 / 设计 / 部署专文
├── VERSION                  # 镜像发版号
└── start.bat                # Windows 本地开发三窗启动
```

| 目录 | 说明 | 生产端口（宿主机） |
|------|------|-------------------|
| `backend/` | 收集器 API + Playwright | 不对外（由 admin 反代 `/api`） |
| `frontend/admin/` | 管理后台 | **8082** |
| `next-web/` | 搜索前端 | **3010** |
| PostgreSQL | `postgres:16-alpine` | **5433** |

更细说明：[docs/架构.md](./docs/架构.md) · [docs/设计说明.md](./docs/设计说明.md)

---

## Docker 镜像

### Docker Hub（NAS 推荐）

| 服务 | 当前标签 |
|------|----------|
| 后端 | [`poillysky/sehuatang-backend:1.0.4`](https://hub.docker.com/r/poillysky/sehuatang-backend) |
| 管理 | [`poillysky/sehuatang-admin:1.0.4`](https://hub.docker.com/r/poillysky/sehuatang-admin) |
| 搜索 | [`poillysky/sehuatang-search:1.0.4`](https://hub.docker.com/r/poillysky/sehuatang-search) |

账号：https://hub.docker.com/u/poillysky

每次发版会推送 **版本号**（如 `1.0.4`）和 **`latest`（始终指向当前最新版）**。历史版本号会留在 Hub（`1.0.1`、`1.0.2`、`1.0.3`、`1.0.4`…），NAS Compose 用固定版本号钉住。

发版前若只要清掉「还没版本号时」的杂标签：Hub → Tags → 删除多余短 SHA 等即可，**不要删已发布的版本号标签**。

### GHCR（可选）

- `ghcr.io/poillysky/sehuatang-backend:1.0.4`
- `ghcr.io/poillysky/sehuatang-admin:1.0.4`
- `ghcr.io/poillysky/sehuatang-search:1.0.4`

CI：`.github/workflows/docker.yml`（`RELEASE_TAG` + `latest`）。

---

## NAS 部署（推荐）

### 1. 目录

```text
/vol1/1000/Docker/sehuatang/
├── docker-compose.nas.yml   # 从仓库 deploy/ 拷贝
├── update.sh                # 可选
└── data/
    ├── postgres/            # 库数据
    ├── backend/             # Cookie、预览等
    ├── search/              # 115 Cookie 等
    └── search-cache/        # Next 缓存（可丢）
```

### 2. 启动

```bash
cd /vol1/1000/Docker/sehuatang
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
# 或: sh update.sh
```

### 3. 访问

| 地址 | 说明 |
|------|------|
| `http://NAS_IP:3010` | 搜索 |
| `http://NAS_IP:8082` | 管理（Nginx 反代 `/api` → backend） |
| `NAS_IP:5433` | PostgreSQL（工具直连） |

默认账号（**务必改**）：

- 管理：`admin` / `admin123`（Compose `INITIAL_ADMIN_*`）
- 数据库：见 Compose 中 `POSTGRES_*`

### 4. 迁入已有库数据（只做一次）

停旧栈后（勿加 `-v`、勿删旧数据目录），把旧 Postgres 数据目录拷到  
`/vol1/1000/Docker/sehuatang/data/postgres`，再 `up -d`。

细则见 [docs/部署.md](./docs/部署.md)。

### 5. 升级镜像

更新 Compose 中的版本标签后：

```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

---

## 爬虫行为（摘要）

- 列表统一按发帖时间排序。
- **每天一次**从首页捕新：翻到「整页已入库」即停；**当天后续循环只深扫、不再读第 1 页**。
- 深扫按板块游标续爬（结束页重叠 1 页）；连续全已知可早停。
- 需满龄的板块：未满龄帖延期入队，到期再抓。
- 待抓积压过大时先消化队列，暂缓读列表。

配置：管理端 → 论坛 / 爬虫设置。

---

## 本地开发

Windows 可双击根目录 `start.bat`。

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn api.main:app --reload --port 8080

# 管理端
cd frontend/admin && npm install && npm run dev

# 搜索端
cd next-web && npm install && npm run dev
```

---

## 数据与迁移

- 资源表：下载链主体 + 来源元数据（标题、描述、预览、论坛 / 板块、入库判定等）
- 爬虫队列：待抓 / 已抓帖页
- 鉴权：管理账号与角色

Backend 启动时自动跑待执行 SQL 迁移。

---

## 搜索端 115

在搜索站「115 设置」填写 Cookie 与目录。  
带解压密码转存时：轮询离线任务（最长约 **30 秒**），就绪后立即云解压到同名文件夹，**不删除压缩包**。需 VIP。

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/架构.md](./docs/架构.md) | 组件职责、数据流、NAS 拓扑 |
| [docs/设计说明.md](./docs/设计说明.md) | 产品边界与设计取舍 |
| [docs/部署.md](./docs/部署.md) | 部署细则、目录、更新 |
| [deploy/README.md](./deploy/README.md) | Compose 目录约定 |

---

## 仓库与发版

- GitHub：https://github.com/poillysky/sehua  
- 下次发 **1.0.5**：改 `VERSION`、`deploy/docker-compose.nas.yml` 镜像标签、workflow 的 `RELEASE_TAG`，提交并打 `v1.0.5`
- Hub 上会留下 `1.0.1`、`1.0.2`、`1.0.3`、`1.0.4`…；`latest` 指向最新一次发版

---

## 声明

仅供个人学习与局域网自用；请遵守目标站点与当地法规，勿用于未授权传播。
