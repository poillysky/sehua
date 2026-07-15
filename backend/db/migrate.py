"""Apply SQL migrations under database/migrations (schema_migrations tracked)."""

from __future__ import annotations

import logging
from pathlib import Path

from db.connection import try_postgres

logger = logging.getLogger(__name__)

# 已有 tang98 crawl_* / content_items，跳过会冲突或已由 014 覆盖的原版脚本
SKIP_ON_EXISTING_DB = {
    "001_init.sql",
    "003_crawl_pages.sql",
    "005_crawl_boards.sql",
    "010_crawl_activity.sql",
    "011_crawl_link_kind.sql",
    "012_crawl_forum_id.sql",
}


def migrations_dir() -> Path:
    """Repo: <root>/database/migrations；Docker: /database/migrations。"""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "database" / "migrations",  # 本地 monorepo / 镜像内 /database
        Path("/database/migrations"),
        here.parents[1] / "database" / "migrations",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def run_migrations(*, only: set[str] | None = None) -> list[str]:
    """Apply pending *.sql. Returns list of newly applied filenames."""
    init_dir = migrations_dir()
    sql_files = sorted(init_dir.glob("*.sql"))
    if not sql_files:
        raise FileNotFoundError(f"未找到 SQL 脚本: {init_dir}")

    conn = try_postgres()
    conn.autocommit = True
    applied: list[str] = []

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                  filename TEXT PRIMARY KEY,
                  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            for sql_path in sql_files:
                name = sql_path.name
                if only is not None and name not in only:
                    continue
                if name in SKIP_ON_EXISTING_DB and only is None:
                    # 仍记录为跳过，避免以后误跑
                    cur.execute(
                        "SELECT 1 FROM schema_migrations WHERE filename = %s",
                        (name,),
                    )
                    if not cur.fetchone():
                        cur.execute(
                            "INSERT INTO schema_migrations (filename) VALUES (%s)",
                            (f"skipped:{name}",),
                        )
                        logger.info("skip conflicting migration: %s", name)
                    continue

                cur.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s",
                    (name,),
                )
                if cur.fetchone():
                    logger.info("already applied: %s", name)
                    continue

                sql = sql_path.read_text(encoding="utf-8")
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (name,),
                )
                applied.append(name)
                logger.info("applied: %s", name)
    finally:
        conn.close()

    return applied


def ensure_ed2k_schema() -> None:
    """Ensure ed2k resource + crawler + auth tables exist (idempotent).

    搜索-only 库可能只有 ed2k_resources、没有 crawl_*；此处补齐采集所需表。
    """
    run_migrations(
        only={
            "002_collector_settings.sql",
            "003_crawl_pages.sql",
            "004_discuz_crawler_settings.sql",
            "005_crawl_boards.sql",
            "010_crawl_activity.sql",
            "011_crawl_link_kind.sql",
            "012_crawl_forum_id.sql",
            "014_ed2k_resources_align.sql",
            "015_crawl_queue_retry.sql",
            "016_resource_sources_unique_hash.sql",
            "017_resource_import_outcome.sql",
        }
    )
