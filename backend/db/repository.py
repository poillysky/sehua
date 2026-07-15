"""ED2K-aligned resource repository (hash-centric, matches ed2k collector)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from parsers.ed2k import Ed2kLink, build_search_string

logger = logging.getLogger(__name__)

STUB_LINK_PREFIX = "unavailable://thread/"
_schema_ready = False

# forum_id → 展示名（人工导入可能直接把中文名写入 forum_id）
FORUM_DISPLAY_NAMES: dict[str, str] = {
    "sehuatang": "色花堂",
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
  WHEN lower(COALESCE(r.ed2k_link, '')) LIKE 'unavailable://thread/%%' THEN 'stub'
  WHEN lower(COALESCE(r.ed2k_link, '')) LIKE 'magnet:%%' THEN 'magnet'
  WHEN lower(COALESCE(r.ed2k_link, '')) LIKE 'ed2k://%%' THEN 'ed2k'
  ELSE 'failed'
END
"""


def thread_stub_hash(source_url: str) -> str:
    return hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:32].upper()


def infer_resource_link_kind(ed2k_link: str | None) -> str:
    link = (ed2k_link or "").strip().lower()
    if link.startswith(STUB_LINK_PREFIX.lower()):
        return "stub"
    if link.startswith("magnet:"):
        return "magnet"
    if link.startswith("ed2k://"):
        return "ed2k"
    return "failed"


def _ensure_resource_schema(conn: Any) -> None:
    global _schema_ready
    if _schema_ready:
        return
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS extract_password TEXT"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS preview_images TEXT[]"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS ed2k_links TEXT[]"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS import_outcome TEXT"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS board_fid TEXT"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS board_name TEXT"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS forum_id TEXT"
        )
        cur.execute(
            "ALTER TABLE resource_sources ADD COLUMN IF NOT EXISTS description TEXT"
        )
    conn.commit()
    _schema_ready = True


def ensure_source(
    conn: Any,
    key: str,
    name: str,
    source_type: str,
    url: str | None = None,
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
    *,
    commit: bool = True,
) -> bool:
    _ensure_resource_schema(conn)
    search_string = build_search_string(
        link.filename,
        title or "",
        description or "",
        extract_password or "",
    )

    with conn.cursor() as cur:
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
              ed2k_links, extract_password, board_fid, board_name, forum_id, import_outcome
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO UPDATE SET
              source_id = EXCLUDED.source_id,
              source_url = COALESCE(EXCLUDED.source_url, resource_sources.source_url),
              title = COALESCE(EXCLUDED.title, resource_sources.title),
              description = COALESCE(NULLIF(EXCLUDED.description, ''), resource_sources.description),
              preview_images = CASE
                WHEN coalesce(array_length(EXCLUDED.preview_images, 1), 0) > 0
                  THEN EXCLUDED.preview_images
                ELSE resource_sources.preview_images
              END,
              ed2k_links = CASE
                WHEN coalesce(array_length(EXCLUDED.ed2k_links, 1), 0) > 0
                  THEN EXCLUDED.ed2k_links
                ELSE resource_sources.ed2k_links
              END,
              extract_password = COALESCE(
                NULLIF(EXCLUDED.extract_password, ''),
                resource_sources.extract_password
              ),
              board_fid = COALESCE(EXCLUDED.board_fid, resource_sources.board_fid),
              board_name = COALESCE(EXCLUDED.board_name, resource_sources.board_name),
              forum_id = COALESCE(EXCLUDED.forum_id, resource_sources.forum_id),
              import_outcome = COALESCE(
                NULLIF(EXCLUDED.import_outcome, ''),
                resource_sources.import_outcome
              )
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


def get_data_overview(conn: Any) -> dict:
    """统计可清空的数据量，供数据管理页展示（对齐 ed2k）。"""

    def _count(sql: str, params: tuple[Any, ...] = ()) -> int:
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row[0] or 0) if row else 0
        except Exception:
            conn.rollback()
            return 0

    return {
        "resources": _count("SELECT COUNT(*) FROM ed2k_resources"),
        "resource_sources": _count("SELECT COUNT(*) FROM resource_sources"),
        "import_jobs": _count("SELECT COUNT(*) FROM import_jobs"),
        "crawl_pages": _count("SELECT COUNT(*) FROM crawl_pages"),
        "crawl_pending": _count(
            """
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread' AND status = 'pending'
            """
        ),
        "crawl_boards": _count("SELECT COUNT(*) FROM crawl_boards"),
        "activity_logs": _count("SELECT COUNT(*) FROM crawl_activity_log"),
        # 兼容旧前端字段
        "sources": _count("SELECT COUNT(*) FROM resource_sources"),
        "boards": _count("SELECT COUNT(*) FROM crawl_boards"),
    }


def purge_resources(conn: Any, *, reset_crawl: bool = True) -> None:
    """清空资源与可选爬取数据；保留设置 / 论坛配置 / 账号。"""
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


def delete_resource_by_hash(conn: Any, resource_hash: str) -> bool:
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
    conn.commit()
    return n > 0


def delete_stub_by_source_url(conn: Any, source_url: str) -> bool:
    """删除某帖对应的占位资源（unavailable://），真磁力/ED2K 不动。"""
    url = (source_url or "").strip()
    if not url:
        return False
    stub_hash = thread_stub_hash(url)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.hash FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            WHERE (r.hash = %s OR rs.source_url = %s)
              AND lower(COALESCE(r.ed2k_link, '')) LIKE %s
            """,
            (stub_hash, url, f"{STUB_LINK_PREFIX.lower()}%"),
        )
        rows = cur.fetchall()
    ok = False
    for row in rows:
        if delete_resource_by_hash(conn, str(row[0])):
            ok = True
    return ok


def list_recent_resources(
    conn: Any,
    *,
    limit: int = 30,
    offset: int = 0,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
    q: str | None = None,
) -> tuple[list[dict], int]:
    """Paginated resource list. Returns (items, total)."""
    where: list[str] = []
    params: list[Any] = []

    if source_type in ("web", "upload", "telegram"):
        where.append("s.source_type = %s")
        params.append(source_type)
    if board_name:
        if board_name in ("未分类", "__empty__"):
            where.append("(rs.board_name IS NULL OR rs.board_name = '')")
        else:
            where.append("COALESCE(rs.board_name, '') = %s")
            params.append(board_name)
    if link_kind in ("magnet", "ed2k", "stub", "failed"):
        where.append(f"({LINK_KIND_SQL}) = %s")
        params.append(link_kind)
    if q:
        where.append(
            "("
            "COALESCE(rs.title, '') ILIKE %s OR "
            "COALESCE(r.filename, '') ILIKE %s"
            ")"
        )
        like = f"%{q}%"
        params.extend([like, like])

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    with conn.cursor() as cur:
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
        total = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT
              rs.id, r.hash, r.filename, r.size, r.ed2k_link, r.updated_at,
              rs.title, rs.description, rs.source_url, rs.board_fid, rs.board_name,
              rs.ed2k_links, rs.extract_password, s.key, s.source_type,
              rs.preview_images,
              COALESCE(NULLIF(rs.import_outcome, ''), NULLIF(cp.outcome, '')) AS import_outcome,
              rs.forum_id
            FROM ed2k_resources r
            JOIN resource_sources rs ON rs.hash = r.hash
            JOIN sources s ON s.id = rs.source_id
            LEFT JOIN crawl_pages cp
              ON cp.page_type = 'thread'
             AND cp.url = rs.source_url
            {where_sql}
            ORDER BY r.updated_at DESC NULLS LAST, r.created_at DESC, rs.id DESC
            LIMIT %s OFFSET %s
            """,
            [*params, limit, offset],
        )
        rows = cur.fetchall()

    out: list[dict] = []
    for row in rows:
        link = row[4] or ""
        description = row[7]
        forum_id = row[17]
        out.append(
            {
                "id": int(row[0]),
                "hash": row[1],
                "filename": row[2],
                "size": row[3],
                "ed2k_link": link,
                "updated_at": row[5].isoformat() if row[5] else None,
                "title": row[6],
                "description": description,
                "source_url": row[8],
                "board_fid": row[9],
                "board_name": row[10],
                "ed2k_links": list(row[11] or []),
                "extract_password": row[12],
                "source_key": row[13],
                "source_type": row[14],
                "preview_images": list(row[15] or []),
                "import_outcome": row[16],
                "forum_id": forum_id,
                "forum_name": resolve_forum_display_name(forum_id, description=description),
                "link_kind": infer_resource_link_kind(link),
            }
        )
    return out, total


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
            where.append("COALESCE(rs.board_name, '') = %s")
            params.append(board_name)
    if link_kind in ("magnet", "ed2k", "stub", "failed"):
        where.append(f"({LINK_KIND_SQL}) = %s")
        params.append(link_kind)
    if q:
        where.append(
            "("
            "COALESCE(rs.title, '') ILIKE %s OR "
            "COALESCE(r.filename, '') ILIKE %s"
            ")"
        )
        like = f"%{q}%"
        params.extend([like, like])
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    return where_sql, params


def list_resource_facets(
    conn: Any,
    *,
    q: str | None = None,
    source_type: str | None = None,
    board_name: str | None = None,
    link_kind: str | None = None,
) -> dict[str, Any]:
    """筛选维度计数：来源/板块/结果各自排除本维，交叉受其它维与搜索影响。"""
    base_join = """
        FROM ed2k_resources r
        JOIN resource_sources rs ON rs.hash = r.hash
        JOIN sources s ON s.id = rs.source_id
    """
    # 来源：受搜索 + 板块 + 结果
    src_where, src_params = _facet_where(q=q, board_name=board_name, link_kind=link_kind)
    # 板块：受搜索 + 来源 + 结果
    board_where, board_params = _facet_where(q=q, source_type=source_type, link_kind=link_kind)
    # 结果：受搜索 + 来源 + 板块
    result_where, result_params = _facet_where(q=q, source_type=source_type, board_name=board_name)

    sources = {"all": 0, "web": 0, "upload": 0, "telegram": 0}
    results = {"all": 0, "magnet": 0, "ed2k": 0, "stub": 0, "failed": 0}
    boards: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) {base_join} {src_where}", src_params)
        sources["all"] = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT COALESCE(NULLIF(s.source_type, ''), 'web') AS st, COUNT(*)
            {base_join} {src_where}
            GROUP BY 1
            """,
            src_params,
        )
        for st, n in cur.fetchall():
            sources[str(st or "web")] = int(n)

        cur.execute(
            f"""
            SELECT
              CASE
                WHEN rs.board_name IS NULL OR rs.board_name = '' THEN '未分类'
                ELSE rs.board_name
              END AS board,
              COUNT(*) AS cnt
            {base_join} {board_where}
            GROUP BY 1
            ORDER BY cnt DESC, board ASC
            """,
            board_params,
        )
        for name, n in cur.fetchall():
            boards.append({"name": str(name), "count": int(n)})

        cur.execute(f"SELECT COUNT(*) {base_join} {result_where}", result_params)
        results["all"] = int(cur.fetchone()[0])

        cur.execute(
            f"""
            SELECT ({LINK_KIND_SQL}) AS kind, COUNT(*) AS cnt
            {base_join} {result_where}
            GROUP BY 1
            """,
            result_params,
        )
        for kind, n in cur.fetchall():
            key = str(kind or "failed")
            if key in results:
                results[key] = int(n)
            else:
                results[key] = int(n)

    return {"sources": sources, "boards": boards, "results": results}
