"""PostgreSQL repository — upsert content_items + dual assets."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from db.config import DatabaseConfig
from parsers.links import DualParseResult

log = logging.getLogger(__name__)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - optional until deps installed
    psycopg2 = None  # type: ignore


class Repository:
    """Thin data access for crawler pipeline. Requires psycopg2."""

    def __init__(self, config: DatabaseConfig | None = None):
        if psycopg2 is None:
            raise RuntimeError("psycopg2 is required: pip install psycopg2-binary")
        self.config = config or DatabaseConfig.from_env()
        self._conn: Any = None

    def connect(self) -> None:
        self._conn = psycopg2.connect(self.config.dsn)
        self._conn.autocommit = False

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Repository:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        if exc[0] is None and self._conn is not None:
            self._conn.commit()
        elif self._conn is not None:
            self._conn.rollback()
        self.close()

    @property
    def conn(self) -> Any:
        if self._conn is None:
            self.connect()
        return self._conn

    def upsert_parsed_thread(
        self,
        parsed: DualParseResult,
        *,
        board_fid: int,
        board_name: str = "",
        source_url: str,
        forum_id: str = "sehuatang",
        source_key: str = "web:crawler",
    ) -> int:
        """Insert/update content item and replace its assets. Returns content_item id."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_items (
                  tid, board_fid, board_name, forum_id, title, description,
                  metadata, preview_images, source_url, primary_link_kind,
                  extract_password, search_string, updated_at
                ) VALUES (
                  %(tid)s, %(board_fid)s, %(board_name)s, %(forum_id)s, %(title)s,
                  %(description)s, %(metadata)s::jsonb, %(preview_images)s,
                  %(source_url)s, %(primary_link_kind)s, %(extract_password)s,
                  %(search_string)s, now()
                )
                ON CONFLICT (forum_id, tid) WHERE tid IS NOT NULL
                DO UPDATE SET
                  board_fid = EXCLUDED.board_fid,
                  board_name = COALESCE(NULLIF(EXCLUDED.board_name, ''), content_items.board_name),
                  title = EXCLUDED.title,
                  description = EXCLUDED.description,
                  metadata = EXCLUDED.metadata,
                  preview_images = EXCLUDED.preview_images,
                  source_url = EXCLUDED.source_url,
                  primary_link_kind = EXCLUDED.primary_link_kind,
                  extract_password = EXCLUDED.extract_password,
                  search_string = EXCLUDED.search_string,
                  updated_at = now()
                RETURNING id
                """,
                {
                    "tid": parsed.tid,
                    "board_fid": board_fid,
                    "board_name": board_name,
                    "forum_id": forum_id,
                    "title": parsed.title,
                    "description": parsed.description,
                    "metadata": json.dumps(parsed.metadata, ensure_ascii=False),
                    "preview_images": parsed.preview_images,
                    "source_url": source_url,
                    "primary_link_kind": parsed.primary_link_kind,
                    "extract_password": parsed.extract_password,
                    "search_string": parsed.search_string,
                },
            )
            content_id = int(cur.fetchone()[0])

            cur.execute("DELETE FROM assets WHERE content_item_id = %s", (content_id,))
            for asset in parsed.assets:
                cur.execute(
                    """
                    INSERT INTO assets (
                      content_item_id, link_kind, hash, filename, size, uri, is_primary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (link_kind, hash) DO UPDATE SET
                      content_item_id = EXCLUDED.content_item_id,
                      filename = EXCLUDED.filename,
                      size = EXCLUDED.size,
                      uri = EXCLUDED.uri,
                      is_primary = EXCLUDED.is_primary
                    """,
                    (
                        content_id,
                        asset.link_kind,
                        asset.hash,
                        asset.filename,
                        asset.size,
                        asset.uri,
                        asset.is_primary,
                    ),
                )

            cur.execute("SELECT id FROM sources WHERE key = %s", (source_key,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    INSERT INTO content_sources (content_item_id, source_id, source_url)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (content_id, row[0], source_url),
                )

        return content_id

    def enqueue_thread(
        self,
        url: str,
        *,
        tid: int,
        board_fid: int,
        title: str = "",
        forum_id: str = "sehuatang",
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawl_pages (
                  forum_id, page_type, url, tid, board_fid, thread_title, status
                ) VALUES (%s, 'thread', %s, %s, %s, %s, 'pending')
                ON CONFLICT (url) DO NOTHING
                """,
                (forum_id, url, tid, board_fid, title),
            )

    def fetch_pending_threads(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, url, tid, board_fid, thread_title, forum_id
                FROM crawl_pages
                WHERE page_type = 'thread'
                  AND status = 'pending'
                  AND (retry_after IS NULL OR retry_after <= now())
                ORDER BY id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]

    def mark_page(
        self,
        page_id: int,
        status: str,
        *,
        outcome: str = "",
        link_kind: Optional[str] = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawl_pages
                SET status = %s,
                    outcome = %s,
                    link_kind = COALESCE(%s, link_kind),
                    updated_at = now()
                WHERE id = %s
                """,
                (status, outcome, link_kind, page_id),
            )
