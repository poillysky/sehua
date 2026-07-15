# 后端 API

资源与鉴权已对齐 **ed2k** 模型（`ed2k_resources` + `resource_sources` + `auth_*`），库：`tang98@192.168.2.38:5433`。

## 启动

```powershell
cd e:\sehuatang\backend
.\.venv\Scripts\Activate.ps1
$env:AUTH_BACKEND="postgres"
$env:POSTGRES_HOST="192.168.2.38"
$env:POSTGRES_PORT="5433"
$env:POSTGRES_DB="tang98"
python scripts\init_db.py          # 幂等：应用 014_ed2k_resources_align
python -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

健康检查：http://127.0.0.1:8080/health → `{"schema":"ed2k","auth_db":"postgres",...}`

## 账号登录

| 项 | 值 |
|----|-----|
| 默认用户 | `admin` |
| 默认密码 | `admin123` |
| 登录 | `POST /api/auth/login` |
| 资源列表 | `GET /api/resources/recent` |
| 数据概览 | `GET /api/system/data-overview` |
| 解析入库 | `POST /parse/thread` + `"persist": true, "source_url": "..."` |

写库入口：`db/persist.py` → `upsert_resource`（与 ed2k 一致）。  
迁移：`database/migrations/014_ed2k_resources_align.sql`（保留原 `content_items` / `crawl_*`，不破坏旧表）。

管理前端：http://localhost:8081/login