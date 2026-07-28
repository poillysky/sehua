# sehua

家庭 NAS 上的 **论坛资源采集与检索全栈**：爬虫入库 · 管理运维 · 全文搜索，一套 Compose 跑通。

[![Version](https://img.shields.io/badge/version-1.2.18-0ea5e9?style=flat-square)](./VERSION)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20React%20%7C%20Next.js%20%7C%20Postgres-64748b?style=flat-square)](#技术栈)
[![Deploy](https://img.shields.io/badge/deploy-Docker%20Hub%20pull%20only-22c55e?style=flat-square)](#nas-部署)
[![License](https://img.shields.io/badge/use-personal%20%2F%20LAN-f59e0b?style=flat-square)](#声明)

镜像由 GitHub Actions 构建并推送 **Docker Hub**（及 GHCR）；NAS **只 pull，不本地 build**。发版递增叠加（`1.0.1` … `1.2.0`），历史标签保留，`latest` 始终指向当前版。主栈 **sehua** 与 **search** 分开构建、分开推送。

---

## 一眼看懂

```mermaid
flowchart LR
  subgraph Edge["访问入口"]
    S["搜索 :3010"]
    A["管理 :8082"]
  end

  subgraph Runtime["Docker Compose"]
    NW["next-web"]
    AD["admin · Nginx"]
    API["backend · FastAPI / Playwright"]
    PG[("PostgreSQL :5433")]
  end

  Forum["目标论坛"]

  S --> NW
  A --> AD
  AD -->|"/api"| API
  NW --> PG
  API --> PG
  API <--> Forum
```

| 组件 | 职责 | 生产端口 |
|------|------|----------|
| **backend** | 列表扫帖 · 详情解析 · 入库 · 重爬 · 资源库备份 | 不对外（经 admin 反代） |
| **admin** | 鉴权、爬虫拓扑、论坛配置、导入与数据管理 | **8082** |
| **next-web** | 搜索 / 浏览 / 详情；可选 115 转存与云解压 | **3010** |
| **PostgreSQL 16** | 资源、来源元数据、爬虫队列、鉴权 | **5433** |

---

## 能力

| | |
|--|--|
| **智能爬取** | 按板块-分类子版（fid:typeid）深扫；每日首页捕新，当日后续轮次只深扫；子版游标续爬至板底后切下一启用板 |
| **结构入库** | 磁力 / ED2K 解析；按板块白名单整理名称、类型、大小、密码等字段；预览图与来源溯源 |
| **运维闭环** | 连续调度 / 扫新帖 / 随机抓帖 / 账号爬占位；异常重试；单份滚动 SQL 备份 |
| **检索体验** | Next.js 搜看一体；详情密码一键复制；115 VIP 转存后轮询并云解压（保留压缩包） |

**刻意不做**：Telegram 监听、NAS 现场编译业务镜像、管理端原生 App。

---

## 技术栈

| 层 | 选型 |
|----|------|
| API / 爬虫 | Python · FastAPI · Playwright · httpx |
| 管理端 | Vite · React · Nginx |
| 搜索端 | Next.js · GraphQL · 直连 Postgres |
| 数据 | PostgreSQL 16 · SQL 迁移（`database/migrations/`） |
| 交付 | multi-arch 镜像 · Compose · GitHub Actions |

---

## Docker 镜像

主栈（sehua）与搜索端**各自独立版本、独立 CI、独立推送**，互不绑定。

| 产品 | 版本文件 | 镜像 | 发版触发 |
|------|----------|------|----------|
| **sehua**（API+管理） | [`VERSION`](./VERSION) | [`poillysky/sehuatang-app`](https://hub.docker.com/r/poillysky/sehuatang-app) | 改主栈代码 / `VERSION`，或打标签 `v1.2.0`；或手动 Run [docker-app](./.github/workflows/docker-app.yml) |
| **search**（搜索站） | [`VERSION.search`](./VERSION.search) | [`poillysky/sehuatang-search`](https://hub.docker.com/r/poillysky/sehuatang-search) | 改 `next-web` / `VERSION.search`，或打标签 `search-v1.2.0`；或手动 Run [docker-search](./.github/workflows/docker-search.yml) |

当前钉版：

| 产品 | 标签 |
|------|------|
| sehua | [`1.2.18`](https://hub.docker.com/r/poillysky/sehuatang-app/tags)（见 `deploy/docker-compose.nas.yml`） |
| search | [`1.2.0`](https://hub.docker.com/r/poillysky/sehuatang-search/tags)（见 `deploy/docker-compose.search.yml`） |

- 发 sehua **不会**自动打 search
- 发 search **不会**自动打 sehua
- Hub 上两个仓库的 `latest` 各自更新，版本号可不同

### GHCR（可选）

```text
ghcr.io/poillysky/sehuatang-app:1.2.18
ghcr.io/poillysky/sehuatang-search:1.2.0
```

---

## NAS 部署

### 目录约定

```text
/vol1/1000/Docker/sehuatang/
├── docker-compose.nas.yml      # 自仓库 deploy/ 拷贝
├── update.sh                   # 可选一键 pull + up
└── data/
    ├── postgres/               # 库文件（可从旧实例迁入）
    ├── backend/                # Cookie、会话、预览缓存
    ├── backups/                # 资源表单份备份 ed2k-resources.sql.gz
    ├── search/                 # 115 等搜索端配置
    └── search-cache/           # Next 缓存（可丢）
```

### 启动

主栈（postgres + sehua-app）与搜索**分开**：

```bash
cd /vol1/1000/Docker/sehuatang
# 主栈 sehua
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
# 或: sh update.sh

# 搜索（可选，另开）
docker compose -f docker-compose.search.yml pull
docker compose -f docker-compose.search.yml up -d
# 或: sh update-search.sh
```

### 访问

| URL | 用途 |
|-----|------|
| `http://NAS_IP:8082` | sehua 管理+API |
| `http://NAS_IP:3010` | 搜索前端（独立 compose） |
| `NAS_IP:5433` | PostgreSQL（工具直连，以本机映射为准） |

默认凭据（**上线后立刻修改**）：

- 管理：`admin` / `admin123`（Compose `INITIAL_ADMIN_*`）
- 数据库：见 Compose `POSTGRES_*`

### 迁入旧库（一次性）

停旧栈（勿 `down -v`、勿删数据目录）→ 将旧 Postgres 目录拷至 `data/postgres` → `up -d`。  
细则：[docs/部署.md](./docs/部署.md) · [deploy/README.md](./deploy/README.md)

### 升级

改 Compose 镜像标签至目标版本后：

```bash
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

---

## 爬虫策略（摘要）

- 列表统一按 **发帖时间** 排序。
- **每天一次**首页捕新：翻到「整页已入库」即停；**当日后续循环只深扫**，不再读第 1 页。
- 深扫按板块游标续爬（结束页重叠 1 页）；连续全已知可早停。
- 需满龄板块：未满龄延期入队，到期再抓。
- 待抓积压过大时优先消化队列，暂缓读列表。
- 游客 Cookie 与 **账号 Cookie** 隔离；账号会话仅用于「账号爬占位」。

配置入口：管理端 → 论坛 / 爬虫。

---

## 仓库结构

```text
sehua/
├── backend/              # FastAPI：爬虫 · 入库 · 管理 API
├── frontend/admin/       # 管理端（Vite + React → 与 backend 打成 app 镜像）
├── next-web/             # 搜索端（Next.js，独立镜像）
├── database/migrations/  # PostgreSQL 迁移
├── deploy/               # NAS Compose（主栈 / 搜索分开）
├── docs/                 # 架构 · 设计 · 部署
├── VERSION               # 当前发版号
├── start.bat             # Windows：只启 sehua（API+管理）
└── start-search.bat      # Windows：只启搜索
```

---

## 本地开发

Windows：

- `start.bat` → **sehua**（API `:8080` + 管理 `:8081`）
- `start-search.bat` → **search**（`:3010`，不跟主栈捆绑）

或分别启动：

```bash
# sehua 后端 → :8080
cd backend && pip install -r requirements.txt
uvicorn api.main:app --reload --port 8080

# sehua 管理 → :8081（开发）
cd frontend/admin && npm install && npm run dev

# 搜索（可选）→ :3010
cd next-web && npm install && npm run dev
```

Backend 启动时自动执行待跑 SQL 迁移。

---

## 数据模型（简）

- **资源**：下载链主体 + 文件名 / 大小 / 检索字段  
- **来源**：标题、结构化描述、预览、论坛 / 板块、入库判定、密码  
- **队列**：待抓 / 已抓帖页与重试状态  
- **鉴权**：管理账号与权限  

管理端支持资源表 **单份覆盖备份**（备份前暂停爬虫，结束后按快照恢复）。

---

## 搜索端 · 115

在搜索站「115 设置」填写 Cookie 与目录。  
带解压密码转存时：轮询离线任务（最长约 **30 秒**），就绪后云解压到同名文件夹，**保留压缩包**（需 VIP）。

---

## 文档

| 文档 | 内容 |
|------|------|
| [docs/架构.md](./docs/架构.md) | 组件职责、数据流、NAS 拓扑 |
| [docs/设计说明.md](./docs/设计说明.md) | 产品边界与取舍 |
| [docs/部署.md](./docs/部署.md) | 部署细则、目录、更新 |
| [deploy/README.md](./deploy/README.md) | Compose 目录约定 |

---

## 发版

仓库：https://github.com/poillysky/sehua

发 **sehua**：改 `VERSION` + `deploy/docker-compose.nas.yml` 镜像标签，提交；打 `v1.2.0` 或 path 触发 [docker-app](./.github/workflows/docker-app.yml)（也可手动 Run）。  
发 **search**：改 `VERSION.search` + `deploy/docker-compose.search.yml` 镜像标签，提交；打 `search-v1.2.0`（或 `v1.2.0-search`）或 path 触发 [docker-search](./.github/workflows/docker-search.yml)。  
两者版本号可不同；一次发版只动其中一个即可。Hub / GHCR 保留历史标签；各产品的 `latest` 各自更新。

---

## 声明

仅供个人学习与局域网自用。请遵守目标站点条款与当地法律法规，勿用于未授权传播或商业用途。
