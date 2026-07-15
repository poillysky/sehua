# NAS 部署（替换现网 ed2k-next-web）

## 拷到 NAS 的文件

只需：

```text
/vol1/1000/Docker/sehuatang/          # 或你喜欢的目录
  docker-compose.nas.yml              # 本仓库 deploy/ 下同名文件
  update.sh                           # 可选
```

**不要删：** `/vol1/1000/Docker/ed2k/postgres`（现网数据库）

## 从旧栈切换（保数据）

旧 compose 一般有 `ed2k-postgres` + `ed2k-next-web`。

```bash
# 1) 停旧栈（不要 -v，不要删 postgres 目录）
cd /path/to/旧compose目录
docker compose down

# 2) 起新栈
cd /vol1/1000/Docker/sehuatang
# 若 GHCR 包仍是 Private：
docker login ghcr.io
docker compose -f docker-compose.nas.yml pull
docker compose -f docker-compose.nas.yml up -d

# 3) 检查
docker compose -f docker-compose.nas.yml ps
curl -s http://127.0.0.1:8080/health
```

| 地址 | 说明 |
|------|------|
| http://NAS_IP:3010 | 搜索（原端口不变） |
| http://NAS_IP:8081 | 管理后台（新增） |
| http://NAS_IP:8080/health | API |
| NAS:5433 | 仍是同一套 ed2k 库 |

## 卷对照

| 路径 | 用途 |
|------|------|
| `/vol1/1000/Docker/ed2k/postgres` | **旧库，必须保留** |
| `/vol1/1000/Docker/ed2k/backend` | 爬虫 cookies / 预览（新建即可） |
| `/vol1/1000/Docker/ed2k/search` | 115 配置（新建；旧站点若有可再拷） |
| `/vol1/1000/Docker/ed2k/search-cache` | Next 缓存（可空） |

账号密码与现网一致：`postgres` / `postgres`，库名 `ed2k`。
