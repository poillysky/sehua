# NAS 部署

## 目录

```text
/vol1/1000/Docker/sehuatang/
  docker-compose.nas.yml
  update.sh                 # 可选
  data/
    postgres/               # 数据库（从旧 ed2k 拷过来）
    backend/                # cookies / 预览
    backups/                # 资源库单份备份 ed2k-resources.sql.gz
    search/                 # 115 配置
    search-cache/           # 可空
```

首次部署可先建目录：

```bash
mkdir -p /vol1/1000/Docker/sehuatang/data/{postgres,backend,backups,search,search-cache}
```

## 保留旧库数据

旧路径：`/vol1/1000/Docker/ed2k/postgres`

```bash
# 先停旧容器
docker compose down   # 在旧项目目录

mkdir -p /vol1/1000/Docker/sehuatang/data
cp -a /vol1/1000/Docker/ed2k/postgres /vol1/1000/Docker/sehuatang/data/postgres

cd /vol1/1000/Docker/sehuatang
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d
```

确认搜索数据还在后，再考虑删除旧 `ed2k` 目录。

## 访问

| 地址 | 说明 |
|------|------|
| http://NAS_IP:3010 | 搜索 |
| http://NAS_IP:8082 | 管理 |
| NAS:5433 | PostgreSQL |

账号：库 `postgres`/`postgres` 库名 `ed2k`；管理默认 `admin`/`admin123`。

## 源码在 NAS 上自建镜像（Actions / Hub 不可用时）

把**整仓**拷到 NAS，例如：

```text
/vol1/1000/Docker/sehuatang/
  docker-compose.nas.yml
  build-on-nas.sh
  src/                 ← 仓库根（含 VERSION、backend、frontend、next-web）
  data/...
```

```bash
cd /vol1/1000/Docker/sehuatang
chmod +x build-on-nas.sh
./build-on-nas.sh 1.1.0          # 打 poillysky/sehuatang-*:1.1.0 + latest
UP=1 ./build-on-nas.sh 1.1.0     # 构建完直接 up -d（不 pull）
```

搜索构建吃内存；node 拉不动可：

```bash
NODE_IMAGE=docker.m.daocloud.io/library/node:20-bookworm-slim UP=1 ./build-on-nas.sh 1.1.0
```

`docker-compose.nas.yml` 里镜像名已是 `poillysky/sehuatang-*:1.1.0`，本地打同名标签即可被 compose 使用，无需推 Hub。
