# NAS 部署

## 目录

```text
/vol1/1000/Docker/sehuatang/
  docker-compose.nas.yml
  update.sh                 # 可选
  data/
    postgres/               # 数据库（从旧 ed2k 拷过来）
    backend/                # cookies / 预览
    search/                 # 115 配置
    search-cache/           # 可空
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
