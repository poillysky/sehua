<div align="center">
<img src=".readme/Logo.svg" width="100" height="100" alt="ED2K-Next-Web" />

<h1>ED2K-Next-Web</h1>

[English](./README.md) / 中文文档

更现代的 ED2K 链接搜索与资源展示平台，使用 [Next.js 14](https://nextjs.org/docs/getting-started) + [NextUI v2](https://nextui.org/) 开发，数据存储于 PostgreSQL。

![Index](.readme/zh_Index.jpg)
![Search](.readme/zh_Search.jpg)

</div>

## 部署说明

### 容器部署

最方便的部署方式是用 Docker Compose：

```bash
docker compose up -d
```

服务默认暴露：

- Web 前端：`http://localhost:3008`
- PostgreSQL：`localhost:5433`

### 翻译功能（独立部署）

翻译服务与主 stack **分离**，单独构建和启动：

```bash
# 1. 构建并启动翻译服务
docker build -t libretranslate-local:latest ./docker/libretranslate
docker compose -f docker-compose.translate.yml up -d

# 2. 在 docker-compose.yml 的 ed2k-next-web.environment 里填写：
#    - TRANSLATE_API_URL=http://192.168.1.100:5000
#    - TRANSLATE_FALLBACK=1

# 3. 启动主服务
docker compose up -d
```

| 环境变量 | 说明 |
|---------|------|
| `TMDB_API_KEY` | **推荐**。查 TMDB 官方片名，如 毒液→Venom |
| `TRANSLATE_API_URL` | 可选，独立部署的 LibreTranslate 地址 |
| `TRANSLATE_FALLBACK` | `1` 自建不可用时回退公网 API |

### 全文搜索优化

搜索能力依赖 `ed2k_resources.filename` 和 `ed2k_resources.search_string` 列。首次部署时 `postgres-init/01-init.sql` 会自动创建 `pg_trgm` 索引。若数据库已存在，可手动执行：

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_filename_trgm
  ON ed2k_resources USING gin (filename gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_ed2k_resources_search_string_trgm
  ON ed2k_resources USING gin (search_string gin_trgm_ops);
```

## 开发指引

开发之前，需要先在项目根目录创建一个 `.env.local` 文件：

```bash
# .env.local
POSTGRES_DB_URL=postgres://postgres:postgres@localhost:5433/ed2k
# 或使用分项配置
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5433
# POSTGRES_USER=postgres
# POSTGRES_PASSWORD=postgres
# POSTGRES_DB=ed2k
```

推荐使用 `pnpm` 作为包管理器。

### 安装依赖

```bash
pnpm install
```

### 开发环境运行

```bash
pnpm run dev
```

### 打包 & 部署

```bash
pnpm run build
pnpm run start
```

## 数据表结构

- `ed2k_resources` — 主资源表（hash、filename、size、ed2k_link 等）
- `resource_sources` — 扩展元数据（title、description、preview_images、ed2k_links 等）

## Credits

- [Next.js](https://nextjs.org/)
- [NextUI](https://nextui.org/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Fluent Emoji](https://github.com/microsoft/fluentui-emoji)

## License

Licensed under the [MIT license](./LICENSE).

## 免责声明

- 本程序为免费开源项目，旨在方便对 ED2K 资源索引数据进行检索和展示，以及学习 Next.js 开发，本程序不涉及采集、存储和下载功能；
- 本程序仅用于学习和研究，不得用于商业用途，使用时请遵守相关法律法规，不得侵犯任何第三方的知识产权；
- 本程序不提供任何支持或保证，由使用者自身滥用本程序导致的一切后果均由使用者自行承担。使用者对本程序的使用即表示接受并同意本声明。
