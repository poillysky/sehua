"""ED2K-aligned resource repository (hash-centric, matches ed2k collector)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from parsers.ed2k import Ed2kLink, build_search_string
from parsers.safe_text import strip_nul, strip_nul_list

logger = logging.getLogger(__name__)

STUB_LINK_PREFIX = "unavailable://thread/"
_schema_ready = False

# forum_id → 展示名（人工导入可能直接把中文名写入 forum_id）
FORUM_DISPLAY_NAMES: dict[str, str] = {
    "sehuatang": "色花堂",
    "2048": "2048",
    "other": "其他论坛",
}


def resolve_forum_display_name(
    forum_id: str | None,
    *,
    description: str | None = None,
) -> str:
    """资源来源论坛展示名。"""
    fid = (forum_id or "").strip()
    if fid in FORUM_DISPLAY_NAMES:
        return FORUM_DISPLAY_NAMES[fid]
    if fid:
        return fid
    text = description or ""
    for marker in ("来源论坛名：", "来源论坛名:"):
        if marker in text:
            line = text.split(marker, 1)[1].splitlines()[0].strip()
            if line:
                return line
    return ""


LINK_KIND_SQL = """
CASE
  WHEN r.ed2k_link LIKE 'unavailable://thread/%%' THEN 'stub'
  WHEN r.ed2k_link LIKE 'magnet:%%' THEN 'magnet'
  WHEN r.ed2k_link LIKE 'ed2k://%%' THEN 'ed2k'
  WHEN r.ed2k_link LIKE '%%115cdn.com/s/%%'
    OR r.ed2k_link LIKE '%%115.com/s/%%' THEN '115share'
  ELSE 'failed'
END
"""

# 处理记录按帖聚合：有 source_url 则同帖多子资源合成一行；无 URL 仍按 hash 一行
RESOURCE_GROUP_KEY_SQL = """
CASE
  WHEN NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL
    THEN 'url:' || BTRIM(rs.source_url)
  ELSE 'hash:' || upper(r.hash)
END
"""

# 仅 resource_sources 表上的同口径分组键（无 ed2k_resources 别名 r）
RESOURCE_GROUP_KEY_RS_SQL = """
CASE
  WHEN NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL
    THEN 'url:' || BTRIM(rs.source_url)
  ELSE 'hash:' || upper(rs.hash)
END
"""

# 同帖 ≥2 条「真」子资源（合集）；占位 stub 不计入。
# 仅作反例文档：禁止注入通用 WHERE（相关子查询全表 GROUP BY 会卡死）。
# 合集查询必须走 _list_multi_asset_* / _multi_asset_url_page。
MULTI_ASSET_URL_SQL = """
NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IN (
  SELECT BTRIM(rs2.source_url)
  FROM resource_sources rs2
  JOIN ed2k_resources r2 ON r2.hash = rs2.hash
  WHERE NULLIF(BTRIM(COALESCE(rs2.source_url, '')), '') IS NOT NULL
  GROUP BY BTRIM(rs2.source_url)
  HAVING COUNT(*) FILTER (
    WHERE COALESCE(r2.ed2k_link, '') NOT LIKE 'unavailable://thread/%%'
  ) > 1
)
"""


def _dedupe_preserve(items: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    out: list[Any] = []
    for x in items:
        if x in seen or x is None:
            continue
        seen.add(x)
        out.append(x)
    return out


def _merge_preview_lists(lists: list[list[str] | None], *, cap: int = 25) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for imgs in lists:
        for u in imgs or []:
            s = (u or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= cap:
                return out
    return out


def thread_stub_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:32].upper()


def name_row_hash(source_url: str, resource_name: str) -> str:
    """同帖同资源名的稳定行键（真链 hash 已被其它帖占用时用）。"""
    raw = f"{(source_url or '').strip()}\n{(resource_name or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40].upper()


def infer_resource_link_kind(ed2k_link: str | None) -> str:
    link = (ed2k_link or "").strip().lower()
    if link.startswith(STUB_LINK_PREFIX.lower()):
        return "stub"
    if link.startswith("magnet:"):
        return "magnet"
    if link.startswith("ed2k://"):
        return "ed2k"
    if "115cdn.com/s/" in link or "115.com/s/" in link:
        return "115share"
    return "failed"


def _ensure_resource_schema(conn: Any) -> None:
    """补缺列（IF NOT EXISTS）；空库先建资源表，避免读列表直接 500。"""
    global _schema_ready
    if _schema_ready:
        return
    needed = (
        "extract_password",
        "preview_images",
        "ed2k_links",
        "import_outcome",
        "board_fid",
        "board_name",
        "forum_id",
        "description",
        "parse_tags",
        "parse_warnings",
    )
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.resource_sources')")
        if cur.fetchone()[0] is None:
            from db.migrate import ensure_resource_db_schema

            ensure_resource_db_schema(conn)
        # 先查已有列，避免冷启动连打 8 次 ALTER（远程库可达数秒）
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'resource_sources'
              AND column_name = ANY(%s)
            """,
            (list(needed),),
        )
        have = {str(r[0]) for r in cur.fetchall()}
        missing = [c for c in needed if c not in have]
        for col in missing:
            if col == "preview_images":
                cur.execute(
                    "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS preview_images TEXT[]"
                )
            elif col == "ed2k_links":
                cur.execute(
                    "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS ed2k_links TEXT[]"
                )
            elif col in ("parse_tags", "parse_warnings"):
                cur.execute(
                    f"ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS {col} TEXT[]"
                )
            else:
                cur.execute(
                    f"ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS {col} TEXT"
                )
        # 索引勿在热路径 CREATE INDEX（易与写入死锁）；updated_at / source_url 由迁移创建
    if missing:
        conn.commit()
    _schema_ready = True


def ensure_source(
    conn: Any,
    key: str,
    name: str,
    source_type: str,
    url: str | None = None,
    *,
    commit: bool = True,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (key, name, source_type, url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (key) DO UPDATE SET
              name = EXCLUDED.name,
              source_type = EXCLUDED.source_type,
              url = COALESCE(EXCLUDED.url, sources.url),
              updated_at = now()
            RETURNING id
            """,
            (key, name, source_type, url),
        )
        source_id = cur.fetchone()[0]
    if commit:
        conn.commit()
    return source_id


def upsert_resource(
    conn: Any,
    link: Ed2kLink,
    source_id: int,
    source_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    preview_images: list[str] | None = None,
    ed2k_links: list[str] | None = None,
    extract_password: str | None = None,
    board_fid: str | None = None,
    board_name: str | None = None,
    forum_id: str | None = None,
    import_outcome: str | None = None,
    parse_tags: list[str] | None = None,
    parse_warnings: list[str] | None = None,
    *,
    commit: bool = True,
) -> bool:
    _ensure_resource_schema(conn)
    title = strip_nul(title) or None
    description = strip_nul(description) or None
    extract_password = strip_nul(extract_password) or None
    board_name = strip_nul(board_name) or None
    import_outcome = strip_nul(import_outcome) or None
    source_url = strip_nul(source_url) or None
    forum_id = strip_nul(forum_id) or None
    board_fid = strip_nul(board_fid) or None
    preview_images = strip_nul_list(preview_images) or None
    ed2k_links = strip_nul_list(ed2k_links) or None
    parse_tags = strip_nul_list(parse_tags) or None
    parse_warnings = strip_nul_list(parse_warnings) or None
    # link fields may carry binary-scanned noise
    link = Ed2kLink(
        filename=strip_nul(link.filename) or link.hash,
        size=int(link.size or 0),
        hash=strip_nul(link.hash) or link.hash,
        link=strip_nul(link.link) or link.link,
    )
    search_string = build_search_string(
        link.filename,
        title or "",
        description or "",
        extract_password or "",
    )

    incoming_url = (source_url or "").strip()
    with conn.cursor() as cur:
        # 行键已被其它帖占用：整单拒写，避免污染 ed2k_resources.filename/size
        if incoming_url and link.hash:
            cur.execute(
                """
                SELECT source_url FROM resource_sources
                WHERE upper(hash) = upper(%s) LIMIT 1
                """,
                (link.hash,),
            )
            owned = cur.fetchone()
            if owned:
                existing_url = (owned[0] or "").strip()
                if existing_url and existing_url != incoming_url:
                    if commit:
                        conn.commit()
                    return False

        cur.execute(
            """
            INSERT INTO ed2k_resources (hash, filename, size, ed2k_link, search_string)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO UPDATE SET
              filename = EXCLUDED.filename,
              size = EXCLUDED.size,
              ed2k_link = EXCLUDED.ed2k_link,
              search_string = CASE
                WHEN length(EXCLUDED.search_string) > length(ed2k_resources.search_string)
                  THEN EXCLUDED.search_string
                ELSE ed2k_resources.search_string
              END,
              updated_at = now()
            """,
            (link.hash, link.filename, link.size, link.link, search_string),
        )

        stored_links = ed2k_links or [link.link]

        cur.execute(
            """
            INSERT INTO resource_sources (
              hash, source_id, source_url, title, description, preview_images,
              ed2k_links, extract_password, board_fid, board_name, forum_id, import_outcome,
              parse_tags, parse_warnings
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO UPDATE SET
              source_id = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.source_id
                ELSE EXCLUDED.source_id
              END,
              -- 禁止后帖用同一 hash 改写其它帖的行（合集主 hash 常重复）
              source_url = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.source_url
                ELSE COALESCE(EXCLUDED.source_url, resource_sources.source_url)
              END,
              title = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.title
                ELSE COALESCE(EXCLUDED.title, resource_sources.title)
              END,
              description = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.description
                ELSE COALESCE(NULLIF(EXCLUDED.description, ''), resource_sources.description)
              END,
              preview_images = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.preview_images
                WHEN coalesce(array_length(EXCLUDED.preview_images, 1), 0) > 0
                  THEN EXCLUDED.preview_images
                ELSE resource_sources.preview_images
              END,
              ed2k_links = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.ed2k_links
                WHEN coalesce(array_length(EXCLUDED.ed2k_links, 1), 0) > 0
                  THEN EXCLUDED.ed2k_links
                ELSE resource_sources.ed2k_links
              END,
              extract_password = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.extract_password
                ELSE COALESCE(
                NULLIF(EXCLUDED.extract_password, ''),
                resource_sources.extract_password
              )
              END,
              board_fid = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.board_fid
                ELSE COALESCE(EXCLUDED.board_fid, resource_sources.board_fid)
              END,
              board_name = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.board_name
                ELSE COALESCE(
                NULLIF(EXCLUDED.board_name, ''),
                resource_sources.board_name
              )
              END,
              forum_id = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.forum_id
                ELSE COALESCE(EXCLUDED.forum_id, resource_sources.forum_id)
              END,
              import_outcome = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.import_outcome
                ELSE COALESCE(
                  NULLIF(EXCLUDED.import_outcome, ''),
                  resource_sources.import_outcome
                )
              END,
              parse_tags = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.parse_tags
                WHEN coalesce(array_length(EXCLUDED.parse_tags, 1), 0) > 0
                  THEN EXCLUDED.parse_tags
                ELSE resource_sources.parse_tags
              END,
              parse_warnings = CASE
                WHEN coalesce(btrim(resource_sources.source_url), '') <> ''
                 AND coalesce(btrim(EXCLUDED.source_url), '') <> ''
                 AND btrim(resource_sources.source_url)
                     IS DISTINCT FROM btrim(EXCLUDED.source_url)
                THEN resource_sources.parse_warnings
                WHEN coalesce(array_length(EXCLUDED.parse_warnings, 1), 0) > 0
                  THEN EXCLUDED.parse_warnings
                ELSE resource_sources.parse_warnings
              END
            """,
            (
                link.hash,
                source_id,
                source_url,
                title,
                description,
                preview_images,
                stored_links,
                extract_password,
                board_fid,
                board_name,
                forum_id,
                (import_outcome or "").strip() or None,
                parse_tags,
                parse_warnings,
            ),
        )

    if commit:
        conn.commit()
    return True


def import_thread_stub(
    conn: Any,
    *,
    source_id: int,
    source_url: str,
    title: str | None = None,
    description: str | None = None,
    preview_images: list[str] | None = None,
    board_fid: str | None = None,
    board_name: str | None = None,
    forum_id: str | None = None,
    import_outcome: str | None = None,
) -> int:
    source_url = (source_url or "").strip()
    if not source_url:
        return 0
    # 同帖已有真链时不再叠占位，避免列表出现「真链 + stub」假 ×2
    if _url_has_real_resource(conn, source_url):
        return 0

    stub_hash = thread_stub_hash(source_url)
    filename = (title or f"thread-{stub_hash[:8]}")[:255]
    stub = Ed2kLink(
        filename=filename,
        size=0,
        hash=stub_hash,
        link=f"{STUB_LINK_PREFIX}{stub_hash}",
    )
    upsert_resource(
        conn,
        stub,
        source_id,
        source_url=source_url,
        title=title,
        description=description,
        preview_images=preview_images,
        ed2k_links=[],
        board_fid=board_fid,
        board_name=board_name,
        forum_id=forum_id,
        import_outcome=import_outcome or "无下载链 · 占位入库",
    )
    return 1


def _url_has_real_resource(conn: Any, source_url: str) -> bool:
    url = (source_url or "").strip()
    if not url:
        return False
    stub_prefix = f"{STUB_LINK_PREFIX}%"
    with conn.cursor() as cur:
        # 等值匹配 source_url，便于走 idx_resource_sources_source_url
        cur.execute(
            """
            SELECT 1
            FROM resource_sources rs
            JOIN ed2k_resources r ON r.hash = rs.hash
            WHERE rs.source_url = %s
              AND r.ed2k_link NOT LIKE %s
            LIMIT 1
            """,
            (url, stub_prefix),
        )
        return cur.fetchone() is not None


def get_data_overview(conn: Any, resource_conn: Any | None = None) -> dict:
    """统计可清空的数据量；资源计数可走独立资源库连接。"""

    rconn = resource_conn or conn

    def _count(c: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
        try:
            with c.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row[0] or 0) if row else 0
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            return 0

    return {
        "resources": _count(rconn, "SELECT COUNT(*) FROM ed2k_resources"),
        "resource_sources": _count(rconn, "SELECT COUNT(*) FROM resource_sources"),
        "import_jobs": _count(rconn, "SELECT COUNT(*) FROM import_jobs"),
        "crawl_pages": _count(conn, "SELECT COUNT(*) FROM crawl_pages"),
        "crawl_pending": _count(
            conn,
            """
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread' AND status = 'pending'
            """,
        ),
        "crawl_boards": _count(conn, "SELECT COUNT(*) FROM crawl_boards"),
        "activity_logs": _count(conn, "SELECT COUNT(*) FROM crawl_activity_log"),
        "sources": _count(rconn, "SELECT COUNT(*) FROM resource_sources"),
        "boards": _count(conn, "SELECT COUNT(*) FROM crawl_boards"),
        "resource_db_separate": bool(resource_conn is not None and resource_conn is not conn),
    }


def purge_resources(conn: Any, *, reset_crawl: bool = True) -> None:
    """清空资源；reset_crawl=True 时一并清空爬取数据。保留设置 / 论坛配置 / 账号。"""
    tables = ["resource_tags", "resource_sources", "import_jobs", "ed2k_resources"]
    if reset_crawl:
        tables.extend(["crawl_pages", "crawl_boards", "crawl_activity_log"])
    with conn.cursor() as cur:
        for name in tables:
            cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
            if cur.fetchone()[0] is None:
                continue
            cur.execute(f"DELETE FROM {name}")
    conn.commit()


def purge_crawl_data(conn: Any) -> None:
    """只清空项目爬取记录（队列/进度/活动日志），不动资源库与账号配置。"""
    tables = ["crawl_pages", "crawl_boards", "crawl_activity_log"]
    with conn.cursor() as cur:
        for name in tables:
            cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
            if cur.fetchone()[0] is None:
                continue
            cur.execute(f"DELETE FROM {name}")
    conn.commit()


def clear_forum_crawl_progress(conn: Any) -> int:
    """清空各论坛配置里的列表游标 / 捕新进度（不清 enabled / Cookie 等）。"""
    return _clear_forum_progress_keys(
        conn,
        (
            "board_list_cursors",
            "board_head_catchup_on",
            "board_head_progress",
            "board_backfill_progress",
        ),
    )


def clear_forum_head_catchup(conn: Any) -> dict[str, int]:
    """只清捕新日期闸门与当日捕新进度页，不动深扫游标 / 队列。"""
    from db.forum_configs import load_forum_configs_map

    configs = load_forum_configs_map(conn)
    date_entries = 0
    progress_entries = 0
    for raw in configs.values():
        dates = (raw or {}).get("board_head_catchup_on") or {}
        progress = (raw or {}).get("board_head_progress") or {}
        if isinstance(dates, dict):
            date_entries += len(dates)
        if isinstance(progress, dict):
            progress_entries += len(progress)
    forums = _clear_forum_progress_keys(
        conn,
        ("board_head_catchup_on", "board_head_progress"),
    )
    return {
        "forums": forums,
        "date_entries": date_entries,
        "progress_entries": progress_entries,
    }


def _clear_forum_progress_keys(conn: Any, keys: tuple[str, ...]) -> int:
    from db.forum_configs import load_forum_configs_map, save_forum_config

    configs = load_forum_configs_map(conn)
    n = 0
    for forum_id, raw in configs.items():
        cfg = dict(raw or {})
        changed = False
        for key in keys:
            if cfg.get(key):
                cfg[key] = {}
                changed = True
        if changed:
            save_forum_config(conn, str(forum_id), cfg)
            n += 1
    return n


def delete_resource_by_hash(
    conn: Any, resource_hash: str, *, commit: bool = True
) -> bool:
    """按 hash 删除单条资源（含 resource_sources / tags）。"""
    h = (resource_hash or "").strip()
    if not h:
        return False
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", ("public.resource_tags",))
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM resource_tags WHERE hash = %s", (h,))
        cur.execute("DELETE FROM resource_sources WHERE hash = %s", (h,))
        cur.execute("DELETE FROM ed2k_resources WHERE hash = %s", (h,))
        n = int(cur.rowcount or 0)
    if commit:
        conn.commit()
    return n > 0


def delete_other_resources_by_source_url(
    conn: Any,
    source_url: str,
    keep_hashes: list[str] | set[str] | tuple[str, ...],
    *,
    commit: bool = True,
) -> int:
    """删除同帖 URL 下不在 keep 集合内的资源行（重爬替换旧真链）。

    keep 为空时不删，避免误清空。
    """
    url = (source_url or "").strip()
    keep = {
        str(h).strip().upper()
        for h in (keep_hashes or [])
        if str(h or "").strip()
    }
    if not url or not keep:
        return 0
    _ensure_resource_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT hash FROM resource_sources
            WHERE source_url = %s
            """,
            (url,),
        )
        victims = [
            str(row[0]).strip().upper()
            for row in cur.fetchall()
            if row and str(row[0] or "").strip().upper() not in keep
        ]
        if not victims:
            return 0
        cur.execute("SELECT to_regclass(%s)", ("public.resource_tags",))
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM resource_tags WHERE hash = ANY(%s)", (victims,))
        cur.execute("DELETE FROM resource_sources WHERE hash = ANY(%s)", (victims,))
        cur.execute("DELETE FROM ed2k_resources WHERE hash = ANY(%s)", (victims,))
    if commit:
        conn.commit()
    return len(victims)


def delete_stub_by_source_url(
    conn: Any, source_url: str, *, commit: bool = True
) -> bool:
    """删除某帖对应的占位资源（unavailable://），真磁力/ED2K 不动。

    必须避免对 ed2k_link 做全表 LOWER/LIKE：旧写法 OR + LIKE 会 seq scan
    ~30 万行，单次真链入库常卡 15–25s。
    """
    url = (source_url or "").strip()
    if not url:
        return False
    stub_hash = thread_stub_hash(url)
    stub_prefix = f"{STUB_LINK_PREFIX}%"
    hashes: set[str] = set()
    with conn.cursor() as cur:
        # 1) 确定性占位 hash（主键）— O(1)
        cur.execute(
            """
            SELECT hash FROM ed2k_resources
            WHERE hash = %s
              AND ed2k_link LIKE %s
            """,
            (stub_hash, stub_prefix),
        )
        for row in cur.fetchall():
            hashes.add(str(row[0]))
        # 2) 同帖 URL 上的遗留占位（依赖 source_url 索引）
        cur.execute(
            """
            SELECT rs.hash
            FROM resource_sources rs
            JOIN ed2k_resources r ON r.hash = rs.hash
            WHERE rs.source_url = %s
              AND r.ed2k_link LIKE %s
            """,
            (url, stub_prefix),
        )
        for row in cur.fetchall():
            hashes.add(str(row[0]))
    ok = False
    for h in hashes:
        if delete_resource_by_hash(conn, h, commit=False):
            ok = True
    if commit and ok:
        conn.commit()
    return ok


def known_resource_tids(
    conn: Any,
    tids: list[int],
    *,
    forum_id: str = "",
    entry_url: str = "",
) -> set[int]:
    """批量查询 resource_sources 中已有的帖 tid（按规范 source_url 等值匹配）。

    禁止 ``LIKE '%thread-{tid}-%'``：前导通配无法走 source_url 索引，
    每页列表扫 ~30 万行可达数秒，NAS CPU 易报警。
    """
    from crawler.list_urls import site_root
    from crawler.sites import get_site_adapter, is_phpwind
    from db.queue import canonical_thread_url, tid_from_url

    clean = sorted({int(t) for t in tids if t is not None and int(t) > 0})
    if not clean:
        return set()
    _ensure_resource_schema(conn)
    fid = (forum_id or "").strip() or "sehuatang"
    root = site_root(entry_url) if entry_url else ""
    urls: list[str] = []
    if is_phpwind(fid):
        adapter = get_site_adapter(fid)
        base = root or "https://fby.tfzqs88.com"
        for tid in clean:
            urls.append(
                canonical_thread_url(adapter.build_thread_url(base, tid), forum_id=fid)
            )
    else:
        for tid in clean:
            urls.append(
                canonical_thread_url(f"https://www.sehuatang.net/thread-{tid}-1-1.html")
            )
            if root and "sehuatang." not in root.lower():
                urls.append(canonical_thread_url(f"{root}thread-{tid}-1-1.html"))
    urls = list(dict.fromkeys(u for u in urls if u))
    if not urls:
        return set()
    with conn.cursor() as cur:
        if fid and fid != "sehuatang":
            cur.execute(
                """
                SELECT source_url
                FROM resource_sources
                WHERE source_url = ANY(%s)
                  AND (forum_id = %s OR forum_id IS NULL OR forum_id = '')
                """,
                (urls, fid),
            )
        else:
            cur.execute(
                """
                SELECT source_url
                FROM resource_sources
                WHERE source_url = ANY(%s)
                """,
                (urls,),
            )
        out: set[int] = set()
        for row in cur.fetchall():
            tid = tid_from_url(str(row[0] or ""))
            if tid is not None:
                out.add(int(tid))
        return out


def update_board_meta_by_tids(
    conn: Any,
    tids: list[int],
    *,
    board_fid: str,
    board_name: str,
    forum_id: str = "",
    entry_url: str = "",
) -> int:
    """按 tid 批量更新资源板块字段；返回更新行数。"""
    from crawler.list_urls import site_root
    from crawler.sites import get_site_adapter, is_phpwind
    from db.queue import canonical_thread_url

    clean = sorted({int(t) for t in tids if t is not None and int(t) > 0})
    if not clean:
        return 0
    _ensure_resource_schema(conn)
    fid_col = str(board_fid or "").strip() or None
    name = (board_name or "").strip() or None
    forum = (forum_id or "").strip() or "sehuatang"
    root = site_root(entry_url) if entry_url else ""
    urls: list[str] = []
    if is_phpwind(forum):
        adapter = get_site_adapter(forum)
        base = root or "https://fby.tfzqs88.com"
        for tid in clean:
            urls.append(
                canonical_thread_url(adapter.build_thread_url(base, tid), forum_id=forum)
            )
    else:
        for tid in clean:
            urls.append(
                canonical_thread_url(f"https://www.sehuatang.net/thread-{tid}-1-1.html")
            )
            if root and "sehuatang." not in root.lower():
                urls.append(canonical_thread_url(f"{root}thread-{tid}-1-1.html"))
    urls = list(dict.fromkeys(u for u in urls if u))
    if not urls:
        return 0
    with conn.cursor() as cur:
        if forum and forum != "sehuatang":
            cur.execute(
                """
                UPDATE resource_sources
                SET board_fid = COALESCE(%s, board_fid),
                    board_name = COALESCE(NULLIF(%s, ''), board_name)
                WHERE source_url = ANY(%s)
                  AND (forum_id = %s OR forum_id IS NULL OR forum_id = '')
                """,
                (fid_col, name or "", urls, forum),
            )
        else:
            cur.execute(
                """
                UPDATE resource_sources
                SET board_fid = COALESCE(%s, board_fid),
                    board_name = COALESCE(NULLIF(%s, ''), board_name)
                WHERE source_url = ANY(%s)
                """,
                (fid_col, name or "", urls),
            )
        n = int(cur.rowcount or 0)
    conn.commit()
    return n


# 账号 Cookie 优先重爬的占位（需回复/付费购买不入队；登录后若判为该类则跳过删占位）
ACCOUNT_STUB_OUTCOMES: tuple[str, ...] = (
    "帖子需论坛登录",
    "无阅读权限 · 占位入库",
    "无权限下载附件",
    "0元购买贴",
)


def _priority_stub_where(
    *,
    exclude_hashes: list[str] | None = None,
    forum_id: str | None = None,
) -> tuple[str, list[Any]]:
    """WHERE 子句 + 参数（不含 ORDER/LIMIT）。"""
    outcomes = list(ACCOUNT_STUB_OUTCOMES)
    # 勿用 lower(COALESCE(ed2k_link))：会逼全表扫；前缀与 STUB_LINK_PREFIX 一致可走 stub 部分索引
    clauses = [
        "r.ed2k_link LIKE %s",
        "rs.source_url IS NOT NULL",
        "rs.source_url <> ''",
        "rs.import_outcome IN %s",
    ]
    params: list[Any] = [f"{STUB_LINK_PREFIX}%", tuple(outcomes)]
    forum = (forum_id or "").strip()
    if forum:
        # 历史空 forum_id 视为色花堂，与资源列表筛选一致
        clauses.append("COALESCE(NULLIF(BTRIM(rs.forum_id), ''), 'sehuatang') = %s")
        params.append(forum)
    excl = [h for h in (exclude_hashes or []) if h]
    if excl:
        clauses.append("r.hash NOT IN %s")
        params.append(tuple(excl))
    return " AND ".join(clauses), params


def count_priority_account_stubs(
    conn: Any,
    *,
    exclude_hashes: list[str] | None = None,
    forum_id: str | None = None,
) -> int:
    """优先占位队列条数（可排除本轮已尝试 hash）。"""
    _ensure_resource_schema(conn)
    where_sql, params = _priority_stub_where(
        exclude_hashes=exclude_hashes, forum_id=forum_id
    )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE {where_sql}
            """,
            tuple(params),
        )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


def list_priority_account_stubs(
    conn: Any,
    *,
    limit: int = 1,
    offset: int = 0,
    exclude_hashes: list[str] | None = None,
    q: str | None = None,
    reason: str | None = None,
    forum_id: str | None = None,
) -> list[dict[str, Any]]:
    """捞出需登录 / 无阅读权限 / 无权限下载附件的占位帖，供账号重爬。"""
    _ensure_resource_schema(conn)
    n = max(1, int(limit or 1))
    off = max(0, int(offset or 0))
    outcomes = list(ACCOUNT_STUB_OUTCOMES)
    order_case = " ".join(
        f"WHEN rs.import_outcome = %s THEN {i}" for i, _ in enumerate(outcomes)
    )
    where_sql, where_params = _priority_stub_where(
        exclude_hashes=exclude_hashes, forum_id=forum_id
    )
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            r.hash ILIKE %s
            OR COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, r.filename, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like, like]
    reason_text = (reason or "").strip()
    reason_sql = ""
    reason_params: list[Any] = []
    if reason_text:
        reason_sql = "AND COALESCE(NULLIF(TRIM(rs.import_outcome), ''), '') = %s"
        reason_params = [reason_text]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              r.hash,
              r.ed2k_link,
              rs.source_url,
              rs.import_outcome,
              rs.board_fid,
              rs.board_name,
              rs.forum_id,
              COALESCE(rs.title, r.filename, '') AS title,
              COALESCE(r.updated_at, rs.created_at) AS updated_at
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE {where_sql}
              {q_sql}
              {reason_sql}
            ORDER BY
              CASE
                {order_case}
                ELSE 99
              END ASC,
              COALESCE(r.updated_at, rs.created_at) ASC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            (
                *where_params,
                *q_params,
                *reason_params,
                *outcomes,
                n,
                off,
            ),
        )
        cols = [d[0] for d in cur.description]
        rows: list[dict[str, Any]] = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            val = item.get("updated_at")
            if hasattr(val, "isoformat"):
                item["updated_at"] = val.isoformat()
            rows.append(item)
        return rows


def list_priority_account_stub_reasons(
    conn: Any,
    *,
    exclude_hashes: list[str] | None = None,
    q: str | None = None,
    forum_id: str | None = None,
) -> list[dict[str, Any]]:
    """优先占位原因分组（供下拉筛选）。"""
    _ensure_resource_schema(conn)
    where_sql, params = _priority_stub_where(
        exclude_hashes=exclude_hashes, forum_id=forum_id
    )
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            r.hash ILIKE %s
            OR COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, r.filename, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like, like]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(rs.import_outcome), ''), '') AS reason, COUNT(*) AS cnt
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE {where_sql}
              {q_sql}
              AND COALESCE(NULLIF(TRIM(rs.import_outcome), ''), '') <> ''
            GROUP BY 1
            ORDER BY cnt DESC, reason ASC
            LIMIT 80
            """,
            (*params, *q_params),
        )
        return [
            {"reason": str(r[0]), "count": int(r[1] or 0)}
            for r in cur.fetchall()
            if r and r[0]
        ]


def count_priority_account_stubs_q(
    conn: Any,
    *,
    exclude_hashes: list[str] | None = None,
    q: str | None = None,
    reason: str | None = None,
    forum_id: str | None = None,
) -> int:
    """优先占位计数（可带搜索）。"""
    _ensure_resource_schema(conn)
    where_sql, params = _priority_stub_where(
        exclude_hashes=exclude_hashes, forum_id=forum_id
    )
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            r.hash ILIKE %s
            OR COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, r.filename, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like, like]
    reason_text = (reason or "").strip()
    reason_sql = ""
    reason_params: list[Any] = []
    if reason_text:
        reason_sql = "AND COALESCE(NULLIF(TRIM(rs.import_outcome), ''), '') = %s"
        reason_params = [reason_text]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(*)
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE {where_sql}
              {q_sql}
              {reason_sql}
            """,
            (*params, *q_params, *reason_params),
        )
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


# 填槽验收不合格（仍入库）：import_outcome 以「不合格」开头
FRAME_FAIL_REASON_SQL = """
CASE
  WHEN rs.import_outcome LIKE '不合格：结构%%' THEN '不合格：结构'
  WHEN rs.import_outcome LIKE '不合格：容量%%' THEN '不合格：容量'
  ELSE split_part(COALESCE(rs.import_outcome, ''), ' · ', 1)
END
"""


def _frame_fail_where(
    *,
    status: str | None = "all",
    forum_id: str | None = None,
) -> tuple[str, list[Any]]:
    """按帖聚合前的 WHERE（resource_sources rs）。"""
    clauses = [
        "NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL",
        "rs.import_outcome LIKE %s",
    ]
    params: list[Any] = ["不合格%"]
    st = (status or "all").strip().lower()
    if st in {"structure", "结构"}:
        clauses.append("rs.import_outcome LIKE %s")
        params.append("不合格：结构%")
    elif st in {"capacity", "容量"}:
        clauses.append("rs.import_outcome LIKE %s")
        params.append("不合格：容量%")
    forum = (forum_id or "").strip()
    if forum:
        clauses.append("COALESCE(NULLIF(BTRIM(rs.forum_id), ''), 'sehuatang') = %s")
        params.append(forum)
    return " AND ".join(clauses), params


def count_frame_fail_posts(
    conn: Any,
    *,
    status: str | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
    reason: str | None = None,
) -> dict[str, int]:
    """验收不合格帖数（按 source_url 去重）。"""
    _ensure_resource_schema(conn)
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like]
    reason_text = (reason or "").strip()
    reason_sql = ""
    reason_params: list[Any] = []
    if reason_text:
        reason_sql = f"AND ({FRAME_FAIL_REASON_SQL.strip()}) = %s"
        reason_params = [reason_text]

    def _n(st: str) -> int:
        where_sql, params = _frame_fail_where(status=st, forum_id=forum_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(DISTINCT BTRIM(rs.source_url))
                FROM resource_sources rs
                WHERE {where_sql}
                  {q_sql}
                  {reason_sql}
                """,
                (*params, *q_params, *reason_params),
            )
            row = cur.fetchone()
            return int(row[0] or 0) if row else 0

    structure = _n("structure")
    capacity = _n("capacity")
    st = (status or "all").strip().lower()
    if st in {"structure", "结构"}:
        total = structure
    elif st in {"capacity", "容量"}:
        total = capacity
    else:
        total = _n("all")
    return {"structure": structure, "capacity": capacity, "total": total}


def list_frame_fail_posts(
    conn: Any,
    *,
    status: str | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
    reason: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """验收不合格帖明细分页（按 source_url 一行）。"""
    from db.queue import tid_from_url

    _ensure_resource_schema(conn)
    n = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    where_sql, params = _frame_fail_where(status=status, forum_id=forum_id)
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like]
    reason_text = (reason or "").strip()
    reason_sql = ""
    reason_params: list[Any] = []
    if reason_text:
        reason_sql = f"AND ({FRAME_FAIL_REASON_SQL.strip()}) = %s"
        reason_params = [reason_text]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              BTRIM(rs.source_url) AS source_url,
              MAX(COALESCE(rs.title, '')) AS title,
              MAX(COALESCE(rs.import_outcome, '')) AS import_outcome,
              MAX(COALESCE(rs.board_fid, '')) AS board_fid,
              MAX(COALESCE(rs.board_name, '')) AS board_name,
              MAX(COALESCE(rs.forum_id, '')) AS forum_id,
              MAX(rs.hash) AS hash,
              MAX(rs.created_at) AS updated_at
            FROM resource_sources rs
            WHERE {where_sql}
              {q_sql}
              {reason_sql}
            GROUP BY BTRIM(rs.source_url)
            ORDER BY MAX(rs.created_at) DESC NULLS LAST
            LIMIT %s OFFSET %s
            """,
            (*params, *q_params, *reason_params, n, off),
        )
        cols = [d[0] for d in cur.description]
        rows: list[dict[str, Any]] = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            val = item.get("updated_at")
            if hasattr(val, "isoformat"):
                item["updated_at"] = val.isoformat()
            url = str(item.get("source_url") or "")
            item["url"] = url
            tid = tid_from_url(url)
            item["tid"] = tid
            outcome = str(item.get("import_outcome") or "")
            if outcome.startswith("不合格：结构"):
                item["status"] = "structure"
            elif outcome.startswith("不合格：容量"):
                item["status"] = "capacity"
            else:
                item["status"] = "failed"
            item["thread_title"] = item.get("title") or ""
            rows.append(item)
        return rows


def list_frame_fail_reasons(
    conn: Any,
    *,
    status: str | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """不合格原因分组（结构/容量等，按帖去重）。"""
    _ensure_resource_schema(conn)
    where_sql, params = _frame_fail_where(status=status, forum_id=forum_id)
    text = (q or "").strip()
    q_sql = ""
    q_params: list[Any] = []
    if text:
        like = f"%{text}%"
        q_sql = """
          AND (
            COALESCE(rs.source_url, '') ILIKE %s
            OR COALESCE(rs.title, '') ILIKE %s
            OR COALESCE(rs.import_outcome, '') ILIKE %s
            OR COALESCE(rs.board_name, '') ILIKE %s
            OR COALESCE(rs.board_fid, '') ILIKE %s
          )
        """
        q_params = [like, like, like, like, like]
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT reason, COUNT(*) AS cnt
            FROM (
              SELECT
                BTRIM(rs.source_url) AS source_url,
                ({FRAME_FAIL_REASON_SQL.strip()}) AS reason
              FROM resource_sources rs
              WHERE {where_sql}
                {q_sql}
                AND COALESCE(NULLIF(TRIM(rs.import_outcome), ''), '') <> ''
              GROUP BY BTRIM(rs.source_url), ({FRAME_FAIL_REASON_SQL.strip()})
            ) t
            WHERE reason <> ''
            GROUP BY reason
            ORDER BY cnt DESC, reason ASC
            LIMIT 80
            """,
            (*params, *q_params),
        )
        return [
            {"reason": str(r[0]), "count": int(r[1] or 0)}
            for r in cur.fetchall()
            if r and r[0]
        ]


def list_frame_fail_tids(
    conn: Any,
    *,
    status: str | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
    reason: str | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """当前筛选下全部不合格帖 tid + 代表 hash（供全选重爬）。"""
    from db.queue import tid_from_url

    lim = max(1, min(5000, int(limit or 2000)))
    rows = list_frame_fail_posts(
        conn,
        status=status,
        forum_id=forum_id,
        q=q,
        reason=reason,
        limit=lim,
        offset=0,
    )
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows:
        tid = row.get("tid")
        if tid is None:
            tid = tid_from_url(str(row.get("source_url") or ""))
        try:
            n = int(tid) if tid is not None else 0
        except (TypeError, ValueError):
            n = 0
        hash_key = str(row.get("hash") or "").strip()
        if n <= 0 or n in seen or len(hash_key) < 8:
            continue
        seen.add(n)
        out.append({"tid": n, "hash": hash_key, "source_url": row.get("source_url") or ""})
    return out


def _resource_list_where(
    *,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    q: str | None = None,
    forum_id: str | None = None,
) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []

    if source_type in ("web", "upload", "telegram"):
        where.append("s.source_type = %s")
        params.append(source_type)
    if board_name:
        if board_name in ("未分类", "__empty__"):
            where.append("(rs.board_name IS NULL OR rs.board_name = '')")
        else:
            # 主板块名：同时匹配整板与「主板块 · 子类」
            where.append(
                "(COALESCE(rs.board_name, '') = %s"
                " OR COALESCE(rs.board_name, '') LIKE %s)"
            )
            params.extend([board_name, f"{board_name} · %"])
    forum = (forum_id or "").strip()
    if forum and forum != "all":
        # 历史空 forum_id 视为本站色花堂
        where.append("COALESCE(NULLIF(BTRIM(rs.forum_id), ''), 'sehuatang') = %s")
        params.append(forum)
    if link_kind in ("magnet", "ed2k", "stub", "failed", "115share"):
        where.append(f"({LINK_KIND_SQL}) = %s")
        params.append(link_kind)
    elif link_kind == "multi":
        # 禁止注入 MULTI_ASSET_URL_SQL（相关子查询全表 GROUP BY 会卡死）。
        # 合集列表/全选/计数请走 _list_multi_asset_* / _multi_asset_url_page。
        raise ValueError(
            "link_kind='multi' must use dedicated multi-asset query paths, "
            "not _resource_list_where"
        )
    if q:
        # 展示标题（无标题回落 filename）+ 判定文案；不扫描述/search_string
        where.append(
            "("
            "COALESCE(NULLIF(TRIM(rs.title), ''), r.filename) ILIKE %s"
            " OR COALESCE(rs.import_outcome, '') ILIKE %s"
            ")"
        )
        like = f"%{q}%"
        params.extend([like, like])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


def _board_meta_score(board_name: str | None, board_fid: str | None) -> int:
    """同帖多 hash 选展示板块：有中文名/子版优先，拒绝 fid-N / 测试脏名。"""
    name = (board_name or "").strip()
    fid = (board_fid or "").strip()
    if not name and not fid:
        return 0
    low = name.lower()
    if low in {"bench", "test", "tmp", "temp", "debug"}:
        return 0
    if name.lower().startswith("fid-") or name.lower().startswith("fid "):
        return 1 if fid else 0
    score = 10
    if " · " in name or "-" in name:
        score += 20
    if ":" in fid:
        score += 10
    if name:
        score += 5
    if fid:
        score += 2
    return score


def _pick_thread_board_meta(assets_raw: list[dict]) -> tuple[str | None, str | None]:
    """从同帖子资源里挑最可信的 board_fid / board_name（新且分高优先）。"""
    best: tuple[int, int, str | None, str | None] | None = None
    for idx, raw in enumerate(assets_raw or []):
        if not isinstance(raw, dict):
            continue
        fid_raw = raw.get("board_fid")
        name_raw = raw.get("board_name")
        fid = str(fid_raw).strip() if fid_raw not in (None, "") else None
        name = str(name_raw).strip() if name_raw not in (None, "") else None
        score = _board_meta_score(name, fid)
        if score <= 0:
            continue
        # idx 越大通常越新（补全查询 created_at ASC 时靠后；其它路径也宁可要后出现的高分）
        key = (score, idx, fid, name)
        if best is None or key[:2] >= best[:2]:
            best = key
    if not best:
        return None, None
    return best[2], best[3]


def sync_board_meta_by_source_url(
    conn: Any,
    source_url: str,
    *,
    board_fid: str | int | None,
    board_name: str | None,
    forum_id: str | None = None,
    commit: bool = True,
) -> int:
    """同帖所有 hash 行回写板块（重拉新 hash 时盖掉旧脏名）。"""
    url = (source_url or "").strip()
    if not url:
        return 0
    fid_col = str(board_fid).strip() if board_fid not in ("", None) else None
    name = (board_name or "").strip() or None
    if not fid_col and not name:
        return 0
    forum = (forum_id or "").strip() or None
    _ensure_resource_schema(conn)
    with conn.cursor() as cur:
        if forum:
            cur.execute(
                """
                UPDATE resource_sources
                SET board_fid = COALESCE(%s, board_fid),
                    board_name = COALESCE(NULLIF(%s, ''), board_name),
                    forum_id = COALESCE(%s, forum_id)
                WHERE source_url = %s
                """,
                (fid_col, name or "", forum, url),
            )
        else:
            cur.execute(
                """
                UPDATE resource_sources
                SET board_fid = COALESCE(%s, board_fid),
                    board_name = COALESCE(NULLIF(%s, ''), board_name)
                WHERE source_url = %s
                """,
                (fid_col, name or "", url),
            )
        n = int(cur.rowcount or 0)
    if commit:
        conn.commit()
    return n


def _assemble_thread_resource_row(
    *,
    group_id: int,
    updated_at: Any,
    source_key: str | None,
    source_type: str | None,
    import_outcome: str | None,
    assets_raw: list[Any],
) -> dict:
    """同一帖（或无 URL 的单 hash）聚合成处理记录一行。"""
    assets: list[dict] = []
    for raw in assets_raw or []:
        if isinstance(raw, dict):
            item = raw
        else:
            continue
        link = (item.get("ed2k_link") or "").strip()
        assets.append(
            {
                "hash": item.get("hash"),
                "filename": item.get("filename"),
                "size": int(item.get("size") or 0),
                "ed2k_link": link,
                "preview_images": list(item.get("preview_images") or []),
                "link_kind": infer_resource_link_kind(link),
            }
        )
    if not assets:
        return {
            "id": int(group_id),
            "hash": "",
            "hashes": [],
            "filename": "",
            "size": 0,
            "ed2k_link": "",
            "updated_at": updated_at.isoformat() if updated_at else None,
            "title": None,
            "description": None,
            "source_url": None,
            "board_fid": None,
            "board_name": None,
            "ed2k_links": [],
            "extract_password": None,
            "source_key": source_key,
            "source_type": source_type,
            "preview_images": [],
            "import_outcome": import_outcome,
            "forum_id": None,
            "forum_name": "",
            "link_kind": "failed",
            "asset_count": 0,
            "assets": [],
        }

    primary = assets[0]
    # 标题等取首条；板块在同帖多 hash 间另选（避免旧脏名如 bench 盖住重拉结果）
    meta_src = assets_raw[0] if assets_raw and isinstance(assets_raw[0], dict) else {}
    description = meta_src.get("description")
    forum_id = meta_src.get("forum_id")
    board_fid, board_name = _pick_thread_board_meta(
        [a for a in (assets_raw or []) if isinstance(a, dict)]
    )
    if not board_fid and not board_name:
        board_fid = meta_src.get("board_fid")
        board_name = meta_src.get("board_name")
    # forum_id：优先非空
    for raw in reversed([a for a in (assets_raw or []) if isinstance(a, dict)]):
        fid = (raw.get("forum_id") or "").strip()
        if fid:
            forum_id = fid
            break
    hashes = _dedupe_preserve([a["hash"] for a in assets if a.get("hash")])
    links = _dedupe_preserve(
        [a["ed2k_link"] for a in assets if a.get("ed2k_link")]
        + list(meta_src.get("ed2k_links") or [])
    )
    previews = _merge_preview_lists([a.get("preview_images") for a in assets])
    return {
        "id": int(group_id),
        "hash": primary.get("hash") or "",
        "hashes": hashes,
        "filename": primary.get("filename") or "",
        "size": int(primary.get("size") or 0),
        "ed2k_link": primary.get("ed2k_link") or "",
        "updated_at": updated_at.isoformat() if updated_at else None,
        "title": meta_src.get("title"),
        "description": description,
        "source_url": meta_src.get("source_url"),
        "board_fid": board_fid,
        "board_name": board_name,
        "ed2k_links": links,
        "extract_password": meta_src.get("extract_password"),
        "source_key": source_key,
        "source_type": source_type,
        "preview_images": previews,
        "import_outcome": import_outcome,
        "forum_id": forum_id,
        "forum_name": resolve_forum_display_name(forum_id, description=description),
        "link_kind": primary.get("link_kind") or infer_resource_link_kind(primary.get("ed2k_link")),
        "asset_count": len(assets),
        "assets": assets,
    }


def _thread_group_key(source_url: str | None, resource_hash: str) -> str:
    url = (source_url or "").strip()
    if url:
        return f"url:{url}"
    return f"hash:{(resource_hash or '').strip().upper()}"


def _flat_resource_select_sql(where_sql: str) -> str:
    # 不 JOIN crawl_pages：大表关联会把「最近 N 条」拖到数十秒
    return f"""
            SELECT
              rs.id, r.hash, r.filename, r.size, r.ed2k_link, r.updated_at,
              rs.title, rs.description, rs.source_url, rs.board_fid, rs.board_name,
              rs.ed2k_links, rs.extract_password, s.key, s.source_type,
              rs.preview_images,
              rs.import_outcome,
              rs.forum_id
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            {where_sql}
            ORDER BY r.updated_at DESC NULLS LAST, r.created_at DESC, rs.id DESC
            """


def _flat_resource_keys_sql(where_sql: str) -> str:
    """oversample 只取分组键：避免把 description/预览图等大字段拖进 1.2 万行窗口。"""
    return f"""
            SELECT
              rs.id, r.hash, r.updated_at, rs.source_url, r.created_at
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            {where_sql}
            ORDER BY r.updated_at DESC NULLS LAST, r.created_at DESC, rs.id DESC
            """


_FULL_FLAT_SELECT = """
              rs.id, r.hash, r.filename, r.size, r.ed2k_link, r.updated_at,
              rs.title, rs.description, rs.source_url, rs.board_fid, rs.board_name,
              rs.ed2k_links, rs.extract_password, s.key, s.source_type,
              rs.preview_images,
              rs.import_outcome,
              rs.forum_id
"""


def _asset_dict_from_flat_row(row: Any) -> dict:
    return {
        "hash": row[1],
        "filename": row[2],
        "size": row[3],
        "ed2k_link": row[4],
        "preview_images": list(row[15] or []),
        "title": row[6],
        "description": row[7],
        "source_url": row[8],
        "board_fid": row[9],
        "board_name": row[10],
        "ed2k_links": list(row[11] or []),
        "extract_password": row[12],
        "forum_id": row[17],
    }


def _group_flat_rows_in_order(rows: list[Any]) -> tuple[list[str], dict[str, list[Any]]]:
    order: list[str] = []
    groups: dict[str, list[Any]] = {}
    for row in rows:
        key = _thread_group_key(row[8], str(row[1] or ""))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)
    return order, groups


def _group_light_rows_in_order(
    rows: list[Any],
) -> tuple[list[str], dict[str, Any]]:
    """轻量 oversample 行：(id, hash, updated_at, source_url, created_at)。"""
    order: list[str] = []
    first_by_key: dict[str, Any] = {}
    for row in rows:
        key = _thread_group_key(row[3], str(row[1] or ""))
        if key not in first_by_key:
            first_by_key[key] = row
            order.append(key)
    return order, first_by_key


def _fetch_full_rows_for_thread_keys(
    cur: Any,
    page_keys: list[str],
) -> tuple[dict[str, list[Any]], dict[str, list[Any]]]:
    """按本页帖键批量拉全字段子资源。返回 (by_url, by_hash_key)。"""
    urls = [k[4:] for k in page_keys if k.startswith("url:")]
    orphan_hashes = [
        k[5:] for k in page_keys if k.startswith("hash:") and k[5:]
    ]
    by_url: dict[str, list[Any]] = {}
    by_hash: dict[str, list[Any]] = {}
    if urls:
        cur.execute(
            f"""
            SELECT {_FULL_FLAT_SELECT}
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            WHERE rs.source_url = ANY(%s)
            ORDER BY r.created_at ASC NULLS LAST, rs.id ASC
            """,
            (urls,),
        )
        for row in cur.fetchall():
            url = (row[8] or "").strip()
            if not url:
                continue
            by_url.setdefault(url, []).append(row)
    if orphan_hashes:
        cur.execute(
            f"""
            SELECT {_FULL_FLAT_SELECT}
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            WHERE r.hash = ANY(%s)
            ORDER BY r.created_at ASC NULLS LAST, rs.id ASC
            """,
            (orphan_hashes,),
        )
        for row in cur.fetchall():
            key = _thread_group_key(row[8], str(row[1] or ""))
            by_hash.setdefault(key, []).append(row)
    return by_url, by_hash


def _fast_flat_total(
    cur: Any,
    where_sql: str,
    params: list[Any],
    *,
    q: str | None = None,
    capped: bool = False,
) -> int:
    """子资源行数：无筛选用估算；有筛选用上限 COUNT。"""
    if not where_sql.strip():
        cur.execute(
            """
            SELECT COALESCE(c.reltuples, 0)::bigint
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'ed2k_resources'
              AND n.nspname = current_schema()
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row and int(row[0] or 0) > 0:
            return int(row[0])
    if capped or (q or "").strip():
        cap = 5000
        cur.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT 1
              FROM ed2k_resources r
              JOIN resource_sources rs ON rs.hash = r.hash
              JOIN sources s ON s.id = rs.source_id
              {where_sql}
              LIMIT %s
            ) t
            """,
            [*params, cap + 1],
        )
        return int(cur.fetchone()[0])
    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM ed2k_resources r
        JOIN resource_sources rs ON rs.hash = r.hash
        JOIN sources s ON s.id = rs.source_id
        {where_sql}
        """,
        params,
    )
    return int(cur.fetchone()[0])


def _fast_thread_total(
    cur: Any,
    where_sql: str,
    params: list[Any],
    *,
    q: str | None = None,
    capped: bool = False,
) -> int:
    """处理记录条数（按帖聚合）：与列表「一帖一行」口径一致。"""
    # 有筛选时用上限 COUNT，避免全表 GROUP BY 拖死登录/列表
    if capped or (q or "").strip() or where_sql.strip():
        cap = 5000
        cur.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT {RESOURCE_GROUP_KEY_SQL} AS gk
              FROM ed2k_resources r
              JOIN resource_sources rs ON rs.hash = r.hash
              JOIN sources s ON s.id = rs.source_id
              {where_sql}
              GROUP BY 1
              LIMIT %s
            ) t
            """,
            [*params, cap + 1],
        )
        return int((cur.fetchone() or [0])[0] or 0)

    # 无筛选：COUNT(DISTINCT source_url) 随库膨胀可到数秒；短时缓存
    now = time.time()
    cached = _THREAD_TOTAL_CACHE.get("")
    if cached and now - cached[0] < _THREAD_TOTAL_CACHE_TTL_SEC:
        return int(cached[1])

    cur.execute(
        """
        SELECT
          (
            SELECT COUNT(DISTINCT BTRIM(source_url))
            FROM resource_sources
            WHERE NULLIF(BTRIM(COALESCE(source_url, '')), '') IS NOT NULL
          )
          + (
            SELECT COUNT(*)
            FROM resource_sources
            WHERE NULLIF(BTRIM(COALESCE(source_url, '')), '') IS NULL
          )
        """
    )
    total = int((cur.fetchone() or [0])[0] or 0)
    _THREAD_TOTAL_CACHE[""] = (now, total)
    return total


_THREAD_TOTAL_CACHE: dict[str, tuple[float, int]] = {}
_THREAD_TOTAL_CACHE_TTL_SEC = 60.0


def list_recent_resources(
    conn: Any,
    *,
    limit: int = 30,
    offset: int = 0,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    q: str | None = None,
    forum_id: str | None = None,
    compute_total: bool = True,
) -> tuple[list[dict], int | None]:
    """分页处理记录：有来源帖 URL 时按帖聚合（一帖一行），否则按 hash。

    用「最近行轻量 oversample + 内存分组」避免全表 GROUP BY；本页再拉全字段。
    compute_total=False 时跳过总数查询（翻页由前端钉住 total）。
    """
    if (link_kind or "").strip() == "multi":
        return _list_multi_asset_resources(
            conn,
            limit=limit,
            offset=offset,
            source_type=source_type,
            board_name=board_name,
            q=q,
            forum_id=forum_id,
            compute_total=compute_total,
        )

    where_sql, params = _resource_list_where(
        source_type=source_type,
        board_name=board_name,
        link_kind=link_kind,
        q=q,
        forum_id=forum_id,
    )
    limit = max(1, int(limit or 30))
    offset = max(0, int(offset or 0))
    need = offset + limit
    # 合集帖多 hash 会压缩「帖数」；有筛选时加大 oversample，尽量凑满本页帖数
    has_filter = bool(
        (q or "").strip()
        or source_type not in (None, "", "all")
        or board_name not in (None, "", "all")
        or link_kind not in (None, "", "all")
        or forum_id not in (None, "", "all")
    )
    _ensure_resource_schema(conn)

    with conn.cursor() as cur:
        # 总数必须跨页稳定：始终按帖聚合计数，勿用本页 oversample 的 len(order)
        thread_total: int | None = None
        flat_total = 0
        if compute_total:
            thread_total = _fast_thread_total(
                cur, where_sql, params, q=q, capped=has_filter
            )
        if has_filter:
            flat_total = _fast_flat_total(
                cur, where_sql, params, q=q, capped=True
            )

        if has_filter:
            # 匹配行未触顶时一次拉全，避免第 1/2 页窗口不同导致漏帖或顺序跳变
            if flat_total <= 5000:
                fetch_n = min(12000, max(int(flat_total) + 100, need * 50 + 200, 1500))
            else:
                fetch_n = min(12000, max(need * 50 + 200, 3000))
        else:
            # 近期大合集单帖可有几十 hash；*12 会只凑出十来帖，首页像「只有 12 条」
            fetch_n = min(max(need * 80 + 200, limit + 200), 12000)

        rows: list[Any] = []
        order: list[str] = []
        while True:
            cur.execute(
                _flat_resource_keys_sql(where_sql) + " LIMIT %s",
                [*params, fetch_n],
            )
            rows = list(cur.fetchall())
            order, _firsts = _group_light_rows_in_order(rows)
            # 帖数仍不足且还有更大窗口可拉时扩窗再取
            if len(order) >= need or len(rows) < fetch_n or fetch_n >= 12000:
                break
            fetch_n = min(fetch_n * 2, 12000)

        page_keys = order[offset : offset + limit]
        by_url, by_hash = _fetch_full_rows_for_thread_keys(cur, page_keys)

    out: list[dict] = []
    for key in page_keys:
        if key.startswith("url:"):
            asset_rows = by_url.get(key[4:]) or []
        else:
            asset_rows = by_hash.get(key) or []
        if not asset_rows:
            continue
        first = asset_rows[0]
        # 列表展示时间取帖内最新 updated_at（轻量键已按新→旧）
        newest_at = max(
            (r[5] for r in asset_rows if r[5] is not None),
            default=first[5],
        )
        out.append(
            _assemble_thread_resource_row(
                group_id=int(first[0]),
                updated_at=newest_at,
                source_key=first[13],
                source_type=first[14],
                import_outcome=first[16],
                assets_raw=[_asset_dict_from_flat_row(r) for r in asset_rows],
            )
        )

    total: int | None
    if compute_total:
        total = int(thread_total or 0)
        # 跨页禁止改用 len(order)：oversample 窗口随页变化会让总数 180↔177 跳动
        if has_filter and total >= 5000 and len(out) >= limit:
            total = max(total, offset + limit + 1)
    else:
        total = None
    return out, total


# 合集筛选：只在最近 N 行资源上 GROUP BY，避免全表聚合卡死列表/全选
_MULTI_SCAN_WINDOW = 80_000


def _count_multi_asset_threads(
    cur: Any,
    where_sql: str,
    params: list[Any],
    *,
    capped: bool = True,
) -> int:
    """同帖 ≥2 条真子资源（×N）帖数；stub 不计入。

    默认 capped + 近量窗口：避免全表 GROUP BY 拖死列表/全选/facet。
    """
    lim_sql = " LIMIT %s" if capped else ""
    lim_params: list[Any] = [5001] if capped else []

    if not where_sql.strip():
        cur.execute(
            f"""
            SELECT COUNT(*) FROM (
              SELECT BTRIM(t.source_url)
              FROM (
                SELECT rs.source_url, r.ed2k_link
                FROM ed2k_resources r
                JOIN resource_sources rs ON rs.hash = r.hash
                WHERE NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL
                ORDER BY r.updated_at DESC NULLS LAST
                LIMIT %s
              ) t
              GROUP BY 1
              HAVING COUNT(*) FILTER (
                WHERE COALESCE(t.ed2k_link, '') NOT LIKE 'unavailable://thread/%%'
              ) > 1
              {lim_sql}
            ) x
            """,
            [_MULTI_SCAN_WINDOW, *lim_params],
        )
        return int((cur.fetchone() or [0])[0] or 0)

    merged = where_sql.rstrip() + (
        " AND NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL"
    )
    cur.execute(
        f"""
        SELECT COUNT(*) FROM (
          SELECT BTRIM(t.source_url)
          FROM (
            SELECT rs.source_url, r.ed2k_link
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            {merged}
            ORDER BY r.updated_at DESC NULLS LAST
            LIMIT %s
          ) t
          GROUP BY 1
          HAVING COUNT(*) FILTER (
            WHERE COALESCE(t.ed2k_link, '') NOT LIKE 'unavailable://thread/%%'
          ) > 1
          {lim_sql}
        ) x
        """,
        [*params, _MULTI_SCAN_WINDOW, *lim_params],
    )
    return int((cur.fetchone() or [0])[0] or 0)


def _multi_asset_url_page(
    cur: Any,
    where_sql: str,
    params: list[Any],
    *,
    limit: int,
    offset: int = 0,
) -> list[str]:
    """合集帖 URL 分页：近量窗口 GROUP BY，勿用 MULTI_ASSET_URL_SQL 相关子查询。"""
    limit = max(1, int(limit or 30))
    offset = max(0, int(offset or 0))
    if where_sql.strip():
        url_filter = where_sql.rstrip() + (
            " AND NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL"
        )
        inner = f"""
            SELECT rs.source_url, r.ed2k_link, r.updated_at
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            {url_filter}
            ORDER BY r.updated_at DESC NULLS LAST
            LIMIT %s
        """
        inner_params: list[Any] = [*params, _MULTI_SCAN_WINDOW]
    else:
        inner = f"""
            SELECT rs.source_url, r.ed2k_link, r.updated_at
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL
            ORDER BY r.updated_at DESC NULLS LAST
            LIMIT %s
        """
        inner_params = [_MULTI_SCAN_WINDOW]

    cur.execute(
        f"""
        SELECT BTRIM(t.source_url) AS url
        FROM (
          {inner}
        ) t
        GROUP BY 1
        HAVING COUNT(*) FILTER (
          WHERE COALESCE(t.ed2k_link, '') NOT LIKE 'unavailable://thread/%%'
        ) > 1
        ORDER BY MAX(t.updated_at) DESC NULLS LAST
        LIMIT %s OFFSET %s
        """,
        [*inner_params, limit, offset],
    )
    return [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]


def list_resource_ids_for_selection(
    conn: Any,
    *,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    q: str | None = None,
    forum_id: str | None = None,
    limit: int = 2000,
) -> tuple[list[dict], int]:
    """当前筛选下的处理记录 id/hash（按帖聚合；跨页全选）。返回 (items, total)。"""
    lim = max(1, min(int(limit or 2000), 5000))
    if (link_kind or "").strip() == "multi":
        return _list_multi_asset_ids_for_selection(
            conn,
            source_type=source_type,
            board_name=board_name,
            q=q,
            forum_id=forum_id,
            limit=lim,
        )

    where_sql, params = _resource_list_where(
        source_type=source_type,
        board_name=board_name,
        link_kind=link_kind,
        q=q,
        forum_id=forum_id,
    )
    fetch_n = min(max(lim * 8, lim), 12000)

    with conn.cursor() as cur:
        thread_total = _fast_thread_total(cur, where_sql, params, q=q, capped=True)

        cur.execute(
            _flat_resource_keys_sql(where_sql) + " LIMIT %s",
            [*params, fetch_n],
        )
        rows = list(cur.fetchall())

    order, first_by_key = _group_light_rows_in_order(rows)
    page_keys = order[:lim]

    urls = [k[4:] for k in page_keys if k.startswith("url:")]
    hashes_by_url: dict[str, list[str]] = {}
    if urls:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT BTRIM(rs.source_url), r.hash
                FROM ed2k_resources r
                JOIN resource_sources rs ON rs.hash = r.hash
                WHERE rs.source_url = ANY(%s)
                ORDER BY r.created_at ASC NULLS LAST, rs.id ASC
                """,
                (urls,),
            )
            for url, h in cur.fetchall():
                hashes_by_url.setdefault(str(url or "").strip(), []).append(str(h))

    # 代表性行补 title / link（轻量键没有这些列）
    rep_hashes = []
    for key in page_keys:
        row0 = first_by_key.get(key)
        if row0 and row0[1]:
            rep_hashes.append(str(row0[1]))
    meta_by_hash: dict[str, tuple[Any, ...]] = {}
    if rep_hashes:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.hash, rs.id, r.ed2k_link, rs.title, r.filename, rs.source_url
                FROM ed2k_resources r
                JOIN resource_sources rs ON rs.hash = r.hash
                WHERE r.hash = ANY(%s)
                """,
                (rep_hashes,),
            )
            for row in cur.fetchall():
                meta_by_hash[str(row[0])] = row

    items: list[dict] = []
    for key in page_keys:
        light = first_by_key.get(key)
        if not light:
            continue
        rep_h = str(light[1] or "")
        meta = meta_by_hash.get(rep_h)
        if key.startswith("url:"):
            hashes = _dedupe_preserve(hashes_by_url.get(key[4:]) or [rep_h])
        else:
            hashes = _dedupe_preserve([rep_h] if rep_h else [])
        if not hashes:
            continue
        link = (meta[2] if meta else "") or ""
        title = (meta[3] if meta else None) or (meta[4] if meta else None) or hashes[0]
        items.append(
            {
                "id": int(meta[1] if meta else light[0]),
                "hash": hashes[0],
                "hashes": hashes,
                "source_url": (meta[5] if meta else light[3]),
                "title": title,
                "link_kind": infer_resource_link_kind(link),
                "asset_count": len(hashes),
            }
        )

    # 与列表接口一致：按帖聚合总数，勿随本窗口 len(order) 跳动
    total = int(thread_total or 0)
    return items, total


def _list_multi_asset_ids_for_selection(
    conn: Any,
    *,
    source_type: str | None = None,
    board_name: str | None = None,
    q: str | None = None,
    forum_id: str | None = None,
    limit: int = 2000,
) -> tuple[list[dict], int]:
    """×N 合集跨页全选：轻量 GROUP BY，禁止 MULTI_ASSET_URL_SQL 相关子查询。"""
    lim = max(1, min(int(limit or 2000), 5000))
    base_where, params = _resource_list_where(
        source_type=source_type,
        board_name=board_name,
        link_kind=None,
        q=q,
        forum_id=forum_id,
    )
    _ensure_resource_schema(conn)

    with conn.cursor() as cur:
        # 能装进本页则跳过二次全量 COUNT
        urls = _multi_asset_url_page(cur, base_where, params, limit=lim, offset=0)
        if len(urls) < lim:
            total = len(urls)
        else:
            total = _count_multi_asset_threads(cur, base_where, params, capped=True)

    if not urls:
        return [], int(total)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              BTRIM(rs.source_url),
              rs.id,
              r.hash,
              r.ed2k_link,
              rs.title,
              r.filename
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE rs.source_url = ANY(%s)
            ORDER BY r.created_at ASC NULLS LAST, rs.id ASC
            """,
            (urls,),
        )
        rows = list(cur.fetchall())

    by_url: dict[str, list[Any]] = {}
    for row in rows:
        url = str(row[0] or "").strip()
        if not url:
            continue
        link = str(row[3] or "")
        if link.lower().startswith("unavailable://thread/"):
            continue
        by_url.setdefault(url, []).append(row)

    items: list[dict] = []
    for url in urls:
        asset_rows = by_url.get(url) or []
        if len(asset_rows) < 2:
            continue
        first = asset_rows[0]
        hashes = _dedupe_preserve([str(r[2]) for r in asset_rows])
        if not hashes:
            continue
        link = first[3] or ""
        items.append(
            {
                "id": int(first[1]),
                "hash": hashes[0],
                "hashes": hashes,
                "source_url": url,
                "title": (first[4] or first[5] or hashes[0]),
                "link_kind": infer_resource_link_kind(link),
                "asset_count": len(hashes),
            }
        )
    return items, int(total)


def get_resource_by_hash(conn: Any, resource_hash: str) -> dict | None:
    h = (resource_hash or "").strip()
    if not h:
        return None
    _ensure_resource_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              r.hash, r.filename, r.size, r.ed2k_link, r.updated_at,
              rs.title, rs.description, rs.source_url, rs.board_fid, rs.board_name,
              rs.ed2k_links, rs.extract_password, s.key, s.source_type,
              rs.preview_images, rs.forum_id
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            WHERE r.hash = %s
            LIMIT 1
            """,
            (h,),
        )
        row = cur.fetchone()
    if not row:
        return None
    link = row[3] or ""
    description = row[6]
    forum_id = row[15]
    return {
        "hash": row[0],
        "filename": row[1],
        "size": row[2],
        "ed2k_link": link,
        "updated_at": row[4].isoformat() if row[4] else None,
        "title": row[5],
        "description": description,
        "source_url": row[7],
        "board_fid": row[8],
        "board_name": row[9],
        "ed2k_links": list(row[10] or []),
        "extract_password": row[11],
        "source_key": row[12],
        "source_type": row[13],
        "preview_images": list(row[14] or []),
        "forum_id": forum_id,
        "forum_name": resolve_forum_display_name(forum_id, description=description),
        "link_kind": infer_resource_link_kind(link),
    }


def list_resource_boards(conn: Any) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT board_name
            FROM resource_sources
            WHERE board_name IS NOT NULL AND board_name <> ''
            ORDER BY board_name
            """
        )
        return [row[0] for row in cur.fetchall()]


def _facet_where(
    *,
    q: str | None = None,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    forum_id: str | None = None,
) -> tuple[str, list[Any]]:
    # multi 禁止走 MULTI_ASSET_URL_SQL（相关子查询全表 GROUP BY 会卡死）
    kind = None if (link_kind or "").strip() == "multi" else link_kind
    return _resource_list_where(
        q=q,
        source_type=source_type,
        board_name=board_name,
        link_kind=kind,
        forum_id=forum_id,
    )


def _list_multi_asset_resources(
    conn: Any,
    *,
    limit: int = 30,
    offset: int = 0,
    source_type: str | None = None,
    board_name: str | None = None,
    q: str | None = None,
    forum_id: str | None = None,
    compute_total: bool = True,
) -> tuple[list[dict], int | None]:
    """只列出会显示 ×N 的合集帖。"""
    base_where, params = _resource_list_where(
        source_type=source_type,
        board_name=board_name,
        link_kind=None,
        q=q,
        forum_id=forum_id,
    )
    limit = max(1, int(limit or 30))
    offset = max(0, int(offset or 0))
    _ensure_resource_schema(conn)

    with conn.cursor() as cur:
        urls = _multi_asset_url_page(
            cur, base_where, params, limit=limit, offset=offset
        )
        total: int | None = None
        if compute_total:
            if offset == 0 and len(urls) < limit:
                total = len(urls)
            else:
                total = _count_multi_asset_threads(cur, base_where, params, capped=True)

    if not urls:
        return [], total

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_FULL_FLAT_SELECT}
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            WHERE rs.source_url = ANY(%s)
            ORDER BY r.created_at ASC NULLS LAST, rs.id ASC
            """,
            (urls,),
        )
        rows = list(cur.fetchall())

    by_url: dict[str, list[Any]] = {}
    for row in rows:
        url = (row[8] or "").strip()
        if url:
            by_url.setdefault(url, []).append(row)

    out: list[dict] = []
    for url in urls:
        asset_rows = [
            r
            for r in (by_url.get(url) or [])
            if not str(r[4] or "").lower().startswith("unavailable://thread/")
        ]
        if len(asset_rows) < 2:
            continue
        first = asset_rows[0]
        newest_at = max((r[5] for r in asset_rows if r[5] is not None), default=first[5])
        out.append(
            _assemble_thread_resource_row(
                group_id=int(first[0]),
                updated_at=newest_at,
                source_key=first[13],
                source_type=first[14],
                import_outcome=first[16],
                assets_raw=[_asset_dict_from_flat_row(r) for r in asset_rows],
            )
        )
    return out, (int(total) if total is not None else None)


_FACET_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_FACET_CACHE_TTL_SEC = 300.0
_FACET_REFRESHING: set[str] = set()


def _facet_snapshot_path():
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "data" / "resource_facets_cache.json"


def _load_facet_snapshot() -> dict[str, Any] | None:
    try:
        path = _facet_snapshot_path()
        if not path.is_file():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("facets"), dict):
            return raw["facets"]
    except Exception:
        logger.debug("load facet snapshot failed", exc_info=True)
        return None


def _save_facet_snapshot(facets: dict[str, Any]) -> None:
    try:
        path = _facet_snapshot_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"saved_at": time.time(), "facets": facets}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        logger.debug("save facet snapshot failed", exc_info=True)


def _facet_filter_dim(value: str | None) -> str | None:
    v = (value or "").strip()
    return v if v and v != "all" else None


def _global_facets_fresh(now: float | None = None) -> dict[str, Any] | None:
    """内存或磁盘上的无筛选 facets（过期内存则回落快照）。"""
    ts = time.time() if now is None else now
    hit = _FACET_CACHE.get("||||")
    if hit and ts - hit[0] < _FACET_CACHE_TTL_SEC:
        return hit[1]
    snap = _load_facet_snapshot()
    if snap:
        _FACET_CACHE["||||"] = (ts, snap)
        return snap
    if hit:
        return hit[1]
    return None


def _board_thread_count_from_facets(boards: list[Any], board_name: str) -> int:
    """与列表 WHERE 一致：整板名 +「主板块 · 子类」。"""
    name = (board_name or "").strip()
    if not name:
        return 0
    if name in ("未分类", "__empty__"):
        for b in boards:
            if str(b.get("name") or "") in ("未分类", ""):
                return int(b.get("count") or 0)
        return 0
    prefix = f"{name} · "
    total = 0
    for b in boards:
        bn = str(b.get("name") or "")
        if bn == name or bn.startswith(prefix):
            total += int(b.get("count") or 0)
    return total


def _scale_facet_buckets(
    base: dict[str, Any], keys: list[str], target_all: int
) -> dict[str, int]:
    raw_sum = sum(int(base.get(k) or 0) for k in keys) or 1
    out = {
        k: int(round(int(base.get(k) or 0) * target_all / raw_sum)) for k in keys
    }
    drift = target_all - sum(out.values())
    if drift and keys:
        max_k = max(keys, key=lambda k: out[k])
        out[max_k] = max(0, out[max_k] + drift)
    return out


def _facet_all_from_global(
    global_facets: dict[str, Any],
    *,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    forum_id: str | None = None,
) -> int | None:
    """单维筛选时从全局快照取帖数；多维或无法解析返回 None。"""
    st = _facet_filter_dim(source_type)
    bn = _facet_filter_dim(board_name)
    lk = _facet_filter_dim(link_kind)
    fid = _facet_filter_dim(forum_id)
    if sum(1 for x in (st, bn, lk, fid) if x) != 1:
        return None
    sources = global_facets.get("sources") or {}
    results = global_facets.get("results") or {}
    if bn:
        return _board_thread_count_from_facets(global_facets.get("boards") or [], bn)
    if fid:
        for f in global_facets.get("forums") or []:
            if str(f.get("id") or "") == fid:
                return int(f.get("count") or 0)
        return 0
    if st:
        return int(sources.get(st) or 0)
    if lk:
        return int(results.get(lk) or 0)
    return None


def peek_facet_thread_total(
    *,
    q: str | None = None,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    forum_id: str | None = None,
) -> int | None:
    """有筛选帖总数：无搜索词且单维时读侧面栏快照，避免 capped GROUP BY。"""
    if (q or "").strip():
        return None
    global_facets = _global_facets_fresh()
    if not global_facets:
        return None
    return _facet_all_from_global(
        global_facets,
        source_type=source_type,
        board_name=board_name,
        link_kind=link_kind,
        forum_id=forum_id,
    )


def _derive_filtered_facets_from_global(
    global_facets: dict[str, Any],
    *,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    forum_id: str | None = None,
) -> dict[str, Any] | None:
    """无搜索词的单维筛选：侧面栏毫秒级派生，不扫库。"""
    thread_all = _facet_all_from_global(
        global_facets,
        source_type=source_type,
        board_name=board_name,
        link_kind=link_kind,
        forum_id=forum_id,
    )
    if thread_all is None:
        return None

    st = _facet_filter_dim(source_type)
    lk = _facet_filter_dim(link_kind)
    sources_g = global_facets.get("sources") or {}
    results_g = global_facets.get("results") or {}
    boards = list(global_facets.get("boards") or [])
    forums = list(global_facets.get("forums") or [])
    src_keys = ["web", "upload", "telegram"]
    kind_keys = ["magnet", "ed2k", "115share", "stub", "failed"]
    global_all = max(1, int(results_g.get("all") or sources_g.get("all") or 1))
    global_multi = int(results_g.get("multi") or 0)

    if st:
        sources = {k: (thread_all if k == st else 0) for k in src_keys}
        sources["all"] = thread_all
        results = _scale_facet_buckets(results_g, kind_keys, thread_all)
        results["all"] = thread_all
        results["multi"] = int(round(global_multi * thread_all / global_all))
    elif lk == "multi":
        sources = _scale_facet_buckets(sources_g, src_keys, thread_all)
        sources["all"] = thread_all
        results = _scale_facet_buckets(results_g, kind_keys, thread_all)
        results["all"] = thread_all
        results["multi"] = thread_all
    elif lk:
        sources = _scale_facet_buckets(sources_g, src_keys, thread_all)
        sources["all"] = thread_all
        results = {k: (thread_all if k == lk else 0) for k in kind_keys}
        results["all"] = thread_all
        results["multi"] = 0
    else:
        # board / forum
        sources = _scale_facet_buckets(sources_g, src_keys, thread_all)
        sources["all"] = thread_all
        results = _scale_facet_buckets(results_g, kind_keys, thread_all)
        results["all"] = thread_all
        results["multi"] = int(round(global_multi * thread_all / global_all))

    return {
        "sources": sources,
        "boards": boards,
        "results": results,
        "forums": forums,
    }


def _facet_thread_kind_expr(alias: str = "r") -> str:
    """与 LINK_KIND_SQL 同语义，可换表别名。"""
    a = alias
    return f"""
CASE
  WHEN {a}.ed2k_link LIKE 'unavailable://thread/%%' THEN 'stub'
  WHEN {a}.ed2k_link LIKE 'magnet:%%' THEN 'magnet'
  WHEN {a}.ed2k_link LIKE 'ed2k://%%' THEN 'ed2k'
  WHEN {a}.ed2k_link LIKE '%%115cdn.com/s/%%'
    OR {a}.ed2k_link LIKE '%%115.com/s/%%' THEN '115share'
  ELSE 'failed'
END
"""


def list_resource_facets(
    conn: Any,
    *,
    q: str | None = None,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    forum_id: str | None = None,
    _force: bool = False,
) -> dict[str, Any]:
    """筛选维度计数（按帖聚合，与处理记录列表口径一致）。

    无筛选：请求路径只读内存/磁盘快照（毫秒级），全量聚合仅后台/_force；
    有筛选：无搜索词的单维从快照派生；否则近量样本（板块树仍用全局快照）。
    """
    cache_key = "|".join(
        [
            (q or "").strip().lower(),
            (source_type or "").strip(),
            (board_name or "").strip(),
            (link_kind or "").strip(),
            (forum_id or "").strip(),
        ]
    )
    unfiltered = not any(
        [
            (q or "").strip(),
            source_type not in (None, "", "all"),
            board_name not in (None, "", "all"),
            link_kind not in (None, "", "all"),
            forum_id not in (None, "", "all"),
        ]
    )
    global_key = "||||"
    now = time.time()

    def _schedule_bg_refresh() -> None:
        if cache_key in _FACET_REFRESHING:
            return
        import threading

        from db.resource_db import connect_resource

        def _bg() -> None:
            c2 = None
            try:
                c2 = connect_resource()
                list_resource_facets(c2, _force=True)
            except Exception:
                logger.debug("background facet refresh failed", exc_info=True)
            finally:
                _FACET_REFRESHING.discard(cache_key)
                if c2 is not None:
                    try:
                        c2.close()
                    except Exception:
                        pass

        _FACET_REFRESHING.add(cache_key)
        threading.Thread(target=_bg, name="facet-refresh", daemon=True).start()

    if not _force:
        cached = _FACET_CACHE.get(cache_key)
        if cached and now - cached[0] < _FACET_CACHE_TTL_SEC:
            return cached[1]

        # 无筛选：绝不全量算在请求线程（曾与预热并发把接口卡死数十秒）
        if unfiltered:
            snap = _load_facet_snapshot()
            if snap:
                _FACET_CACHE[cache_key] = (now, snap)
                _FACET_CACHE[global_key] = (now, snap)
                _schedule_bg_refresh()
                return snap
            # 尚无快照：立刻回空壳并后台算，列表/筛选按钮不阻塞
            stub = {
                "sources": {"all": 0, "web": 0, "upload": 0, "telegram": 0},
                "boards": [],
                "results": {
                    "all": 0,
                    "magnet": 0,
                    "ed2k": 0,
                    "115share": 0,
                    "stub": 0,
                    "failed": 0,
                    "multi": 0,
                },
                "forums": [],
            }
            _schedule_bg_refresh()
            return stub

        # 有筛选、无搜索词：尽量从全局快照单维派生（毫秒级，conn 可为 None）
        if not (q or "").strip():
            global_facets = _global_facets_fresh(now)
            if global_facets:
                derived = _derive_filtered_facets_from_global(
                    global_facets,
                    source_type=source_type,
                    board_name=board_name,
                    link_kind=link_kind,
                    forum_id=forum_id,
                )
                if derived is not None:
                    _FACET_CACHE[cache_key] = (now, derived)
                    return derived

    if conn is None:
        # 无连接且无法派生：回空壳，避免请求线程卡死
        return {
            "sources": {"all": 0, "web": 0, "upload": 0, "telegram": 0},
            "boards": [],
            "results": {
                "all": 0,
                "magnet": 0,
                "ed2k": 0,
                "115share": 0,
                "stub": 0,
                "failed": 0,
                "multi": 0,
            },
            "forums": [],
        }

    sources = {"all": 0, "web": 0, "upload": 0, "telegram": 0}
    results = {
        "all": 0,
        "magnet": 0,
        "ed2k": 0,
        "115share": 0,
        "stub": 0,
        "failed": 0,
        "multi": 0,
    }
    boards: list[dict[str, Any]] = []
    forums: list[dict[str, Any]] = []
    kind_expr = _facet_thread_kind_expr("r")
    forum_key_sql = "COALESCE(NULLIF(BTRIM(rs.forum_id), ''), 'sehuatang')"

    with conn.cursor() as cur:
        if unfiltered:
            # 单连接顺序聚合：避免 DISTINCT ON 全表排序，也避免多连接并行把库打满
            thread_all = int(_fast_thread_total(cur, "", []))
            sources["all"] = thread_all
            results["all"] = thread_all

            cur.execute(
                """
                SELECT 1
                FROM sources
                WHERE COALESCE(NULLIF(source_type, ''), 'web') <> 'web'
                LIMIT 1
                """
            )
            has_non_web = cur.fetchone() is not None

            cur.execute(
                f"""
                SELECT board, COUNT(*) FROM (
                  SELECT
                    {RESOURCE_GROUP_KEY_RS_SQL} AS gk,
                    MIN(
                      CASE
                        WHEN rs.board_name IS NULL OR rs.board_name = '' THEN '未分类'
                        ELSE rs.board_name
                      END
                    ) AS board
                  FROM resource_sources rs
                  GROUP BY 1
                ) t
                GROUP BY board
                ORDER BY COUNT(*) DESC, board ASC
                """
            )
            boards = [{"name": str(name), "count": int(n)} for name, n in cur.fetchall()]

            cur.execute(
                f"""
                SELECT forum_key, COUNT(*) FROM (
                  SELECT
                    {RESOURCE_GROUP_KEY_RS_SQL} AS gk,
                    MIN({forum_key_sql}) AS forum_key
                  FROM resource_sources rs
                  GROUP BY 1
                ) t
                GROUP BY forum_key
                ORDER BY COUNT(*) DESC, forum_key ASC
                """
            )
            forums = []
            for fid, n in cur.fetchall():
                key = str(fid or "sehuatang")
                forums.append(
                    {
                        "id": key,
                        "name": resolve_forum_display_name(key),
                        "count": int(n),
                    }
                )

            # GROUP BY 按帖取链类型，替代 DISTINCT ON … ORDER BY（可省数秒）
            cur.execute(
                f"""
                SELECT kind, COUNT(*) FROM (
                  SELECT
                    COALESCE(NULLIF(BTRIM(rs.source_url), ''), upper(rs.hash)) AS gk,
                    MIN({kind_expr}) AS kind
                  FROM resource_sources rs
                  JOIN ed2k_resources r ON r.hash = rs.hash
                  GROUP BY 1
                ) t
                GROUP BY kind
                """
            )
            kind_map: dict[str, int] = {}
            for kind, n in cur.fetchall():
                kind_map[str(kind or "failed")] = int(n)

            if not has_non_web:
                src_map = {"web": thread_all, "upload": 0, "telegram": 0}
            else:
                cur.execute(
                    f"""
                    SELECT st, COUNT(*) FROM (
                      SELECT
                        {RESOURCE_GROUP_KEY_RS_SQL} AS gk,
                        MIN(COALESCE(NULLIF(s.source_type, ''), 'web')) AS st
                      FROM resource_sources rs
                      JOIN sources s ON s.id = rs.source_id
                      GROUP BY 1
                    ) t
                    GROUP BY st
                    """
                )
                src_map = {"web": 0, "upload": 0, "telegram": 0}
                for st, n in cur.fetchall():
                    key = str(st or "web")
                    if key in src_map:
                        src_map[key] = int(n)
                    else:
                        src_map["web"] += int(n)

            results["multi"] = int(
                _count_multi_asset_threads(cur, "", [], capped=True) or 0
            )

            for k, n in src_map.items():
                sources[k] = int(n)
            sources["all"] = sum(sources[k] for k in ("web", "upload", "telegram")) or thread_all
            results["all"] = sources["all"]
            for kind, n in kind_map.items():
                results[kind] = int(n)
            kind_sum = sum(
                results.get(k, 0) for k in ("magnet", "ed2k", "115share", "stub", "failed")
            )
            if kind_sum > 0 and abs(kind_sum - int(results["all"])) > max(
                50, int(results["all"]) // 100
            ):
                results["all"] = kind_sum
                if sources["upload"] == 0 and sources["telegram"] == 0:
                    sources["all"] = kind_sum
                    sources["web"] = kind_sum
        else:
            # 有筛选且无法快照派生（多维/搜索）：近量样本；板块树仍用全局快照
            sample_where, sample_params = _facet_where(
                q=q,
                source_type=source_type if source_type not in (None, "", "all") else None,
                board_name=board_name if board_name not in (None, "", "all") else None,
                link_kind=link_kind if link_kind not in (None, "", "all") else None,
                forum_id=forum_id if forum_id not in (None, "", "all") else None,
            )
            peeked_all = peek_facet_thread_total(
                q=q,
                source_type=source_type,
                board_name=board_name,
                link_kind=link_kind,
                forum_id=forum_id,
            )
            if peeked_all is not None:
                thread_all = int(peeked_all)
            else:
                thread_all = _fast_thread_total(
                    cur, sample_where, sample_params, q=q, capped=True
                )
            sources["all"] = int(thread_all)
            results["all"] = int(thread_all)

            sample_limit = 2000 if (q or "").strip() else 3000
            cur.execute(
                f"""
                SELECT
                  rs.source_url,
                  r.hash,
                  rs.board_name,
                  s.source_type,
                  r.ed2k_link,
                  r.updated_at
                FROM ed2k_resources r
                JOIN resource_sources rs ON rs.hash = r.hash
                JOIN sources s ON s.id = rs.source_id
                {sample_where}
                ORDER BY r.updated_at DESC NULLS LAST, r.created_at DESC, rs.id DESC
                LIMIT %s
                """,
                [*sample_params, sample_limit],
            )
            sample = list(cur.fetchall())

            # gk -> (updated_at, source_type, board, link)
            threads: dict[str, tuple[Any, str, str, str]] = {}
            for source_url, h, bname, st, link, updated_at in sample:
                url = (source_url or "").strip()
                gk = f"url:{url}" if url else f"hash:{(h or '').upper()}"
                st_n = (st or "").strip() or "web"
                board_n = (bname or "").strip() or "未分类"
                link_n = (link or "").strip()
                prev = threads.get(gk)
                if prev is None:
                    threads[gk] = (updated_at, st_n, board_n, link_n)
                    continue
                prev_upd = prev[0]
                # 同帖多行时保留更新更晚的（与列表 primary 一致）
                if updated_at is not None and (prev_upd is None or updated_at > prev_upd):
                    threads[gk] = (updated_at, st_n, board_n, link_n)

            sample_n = len(threads) or 1
            scale = (thread_all / sample_n) if thread_all > sample_n else 1.0

            src_counts = {"web": 0, "upload": 0, "telegram": 0}
            kind_counts = {
                "magnet": 0,
                "ed2k": 0,
                "115share": 0,
                "stub": 0,
                "failed": 0,
            }
            for _upd, st_n, _board_n, link_n in threads.values():
                if st_n in src_counts:
                    src_counts[st_n] += 1
                else:
                    src_counts["web"] += 1
                k = infer_resource_link_kind(link_n)
                kind_counts[k if k in kind_counts else "failed"] += 1

            for k, n in src_counts.items():
                sources[k] = int(round(n * scale))
            for k, n in kind_counts.items():
                results[k] = int(round(n * scale))

            # 板块 / 论坛：始终用全局快照，禁止有筛选时再全表 GROUP BY
            global_facets = _global_facets_fresh(now)
            if global_facets:
                boards = list(global_facets.get("boards") or [])
                forums = list(global_facets.get("forums") or [])
            else:
                boards = []
                forums = []

            g_all = int((global_facets or {}).get("results", {}).get("all") or 0) or 1
            g_multi = int((global_facets or {}).get("results", {}).get("multi") or 0)
            results["multi"] = int(round(g_multi * int(thread_all) / g_all))

    out = {"sources": sources, "boards": boards, "results": results, "forums": forums}
    _FACET_CACHE[cache_key] = (now, out)
    if unfiltered:
        _FACET_CACHE[global_key] = (now, out)
        _save_facet_snapshot(out)
    if len(_FACET_CACHE) > 64:
        oldest = sorted(_FACET_CACHE.items(), key=lambda kv: kv[1][0])[:16]
        for k, _ in oldest:
            _FACET_CACHE.pop(k, None)
    return out


def peek_cached_thread_total() -> int | None:
    """无筛选帖总数：优先内存 facets / 磁盘快照，避免再跑 COUNT DISTINCT。"""
    cached = _FACET_CACHE.get("||||")
    if cached:
        try:
            n = int((cached[1].get("results") or {}).get("all") or 0)
            if n > 0:
                return n
        except Exception:
            pass
    snap = _load_facet_snapshot()
    if snap:
        try:
            n = int((snap.get("results") or {}).get("all") or 0)
            if n > 0:
                return n
        except Exception:
            pass
    cached_total = _THREAD_TOTAL_CACHE.get("")
    if cached_total:
        return int(cached_total[1])
    return None


def warm_resource_facets_cache() -> None:
    """后台预热无筛选 facets，避免打开处理记录时侧面栏长时间全 0。"""
    try:
        from db.resource_db import connect_resource

        conn = connect_resource()
        try:
            list_resource_facets(conn, _force=True)
        finally:
            conn.close()
    except Exception:
        logger.debug("warm_resource_facets_cache failed", exc_info=True)