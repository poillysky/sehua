# next-web 独立刮削服务（番号元数据 + 本地封面）

## 本地开发

```bash
cd scrape-web
cp .env.example .env   # 指向资源库 5435
npm install
npm run dev
```

- 健康检查: http://127.0.0.1:9209/health
- 同步刮一张: `POST /api/scrape/SSIS-001?sync=1`
- 入队: `POST /api/scrape/SSIS-001`
- 批量入队: `POST /api/scrape/batch` body `{"codes":["SSIS-001","PRED-002"]}`
- 封面: http://127.0.0.1:9209/covers/SSIS-001.jpg

## 补刮

```bash
npm run backfill -- --limit 200
npm run backfill -- --prefix SSIS --limit 0
npm run backfill -- --dry-run --limit 50
```

## 环境变量

| 变量 | 说明 |
|------|------|
| `POSTGRES_*` / `POSTGRES_DB_URL` | 资源库（与 next-web 同库） |
| `COVERS_DIR` | 封面落盘目录 |
| `PORT` | 默认 9209 |
| `SCRAPE_CONCURRENCY` | worker 并发，默认 3（等待数会一次少 N 条，属正常） |
| `SCRAPE_DELAY_MS` | 任务间隔，默认 800 |
| `SCRAPE_API_TOKEN` | 可选；设置后写接口需 Bearer |
| `HTTP_PROXY` / `HTTPS_PROXY` | 启动时若尚无配置文件则作为默认代理 |
| 设置页「出网代理」 | 写入 `data/scrape-config.json`，立即生效 |

第一期仅 DMM 有码封面；FC2 会记为 missing/skipped。
