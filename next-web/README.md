<div align="center">
<img src=".readme/Logo.svg" width="100" height="100" alt="ED2K-Next-Web" />

<h1>ED2K-Next-Web</h1>

English / [中文文档](./README_zh-CN.md)

A modern ED2K link search and resource display platform, built with [Next.js 14](https://nextjs.org/docs/getting-started) + [NextUI v2](https://nextui.org/), backed by PostgreSQL.

![Index](.readme/en_Index.jpg)
![Search](.readme/en_Search.jpg)

</div>

## Deployment

### Docker Compose

```bash
docker compose up -d
```

Default endpoints:

- Web UI: `http://localhost:3008`
- PostgreSQL: `localhost:5433`

### Translation Service (Optional)

Translation runs as a separate stack:

```bash
docker build -t libretranslate-local:latest ./docker/libretranslate
docker compose -f docker-compose.translate.yml up -d
```

Configure in `docker-compose.yml`:

| Variable | Description |
|----------|-------------|
| `TMDB_API_KEY` | Recommended for official movie/TV titles |
| `TRANSLATE_API_URL` | Self-hosted LibreTranslate URL |
| `TRANSLATE_FALLBACK` | `1` to fall back to public APIs |

### Full-Text Search

Search relies on `ed2k_resources.filename` and `ed2k_resources.search_string`. Indexes are created automatically via `postgres-init/01-init.sql` on first deploy.

## Development

Create `.env.local` in the project root:

```bash
POSTGRES_DB_URL=postgres://postgres:postgres@localhost:5433/ed2k
```

Recommended package manager: `pnpm`.

```bash
pnpm install
pnpm run dev
```

## Database Schema

- `ed2k_resources` — main resource table
- `resource_sources` — extended metadata (title, description, preview images, etc.)

## Credits

- [Next.js](https://nextjs.org/)
- [NextUI](https://nextui.org/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Fluent Emoji](https://github.com/microsoft/fluentui-emoji)

## License

Licensed under the [MIT license](./LICENSE).
