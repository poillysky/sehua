# NAS 部署

## 目录

```text
/vol1/1000/Docker/sehuatang/
  docker-compose.nas.yml      # 主栈 sehua（postgres + app）
  docker-compose.search.yml   # 搜索（独立，可选）
  update.sh                   # 只更新主栈
  update-search.sh            # 只更新搜索
  build-on-nas.sh             # 本机构建（默认只打 app）
  data/
    postgres/
    backend/
    backups/
    search/
    search-cache/
```

```bash
mkdir -p /vol1/1000/Docker/sehuatang/data/{postgres,backend,backups,search,search-cache}
```

## 启动（主栈与搜索分开）

```bash
cd /vol1/1000/Docker/sehuatang

# sehua 主栈
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
# 或: sh update.sh

# 搜索（需要时再开）
docker compose -f docker-compose.search.yml pull
docker compose -f docker-compose.search.yml up -d
# 或: sh update-search.sh
```

| 地址 | 用途 |
|------|------|
| http://NAS_IP:8082 | sehua 管理+API |
| http://NAS_IP:3010 | 搜索（独立 compose） |
| NAS:5433 | PostgreSQL（以本机映射为准） |

默认：`postgres`/`postgres` 库 `ed2k`；管理 `admin`/`admin123`。

## 本机构建镜像

默认**只构建 app**；搜索需显式打开：

```bash
cd /vol1/1000/Docker/sehuatang
chmod +x build-on-nas.sh
./build-on-nas.sh 1.2.0
BUILD_SEARCH=1 ./build-on-nas.sh 1.2.0
UP=1 ./build-on-nas.sh 1.2.0
```

镜像：`poillysky/sehuatang-app`、`poillysky/sehuatang-search`（分开推送，见仓库 `.github/workflows/`）。
