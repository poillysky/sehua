"""DualParseResult → ed2k_resources / resource_sources (aligned with ed2k)."""

from __future__ import annotations

from typing import Any

from db.repository import ensure_source, import_thread_stub, upsert_resource
from parsers.ed2k import Ed2kLink
from parsers.links import DualParseResult


def persist_dual_parse(
    conn: Any,
    parsed: DualParseResult,
    *,
    source_url: str,
    board_fid: int | str = "",
    board_name: str = "",
    forum_id: str = "sehuatang",
    source_key: str = "web:crawler",
    source_name: str = "网站爬虫",
    import_outcome: str | None = None,
) -> dict[str, Any]:
    """Persist one thread parse. Returns {count, stub, hash, link_kind}."""
    source_id = ensure_source(conn, source_key, source_name, "web")
    fid = str(board_fid) if board_fid not in ("", None) else None

    primary = next((a for a in parsed.assets if a.is_primary), None)
    if primary is None and parsed.assets:
        primary = parsed.assets[0]

    if primary is None:
        count = import_thread_stub(
            conn,
            source_id=source_id,
            source_url=source_url,
            title=parsed.title or None,
            description=parsed.description or None,
            preview_images=parsed.preview_images or None,
            board_fid=fid,
            board_name=board_name or None,
            forum_id=forum_id,
            import_outcome=import_outcome or "无下载链 · 占位入库",
        )
        return {
            "count": count,
            "stub": True,
            "hash": None,
            "link_kind": "stub" if count else "failed",
            "import_outcome": import_outcome or "无下载链 · 占位入库",
        }

    same_kind = [a for a in parsed.assets if a.link_kind == primary.link_kind]
    all_uris = [a.uri for a in same_kind] or [primary.uri]
    link = Ed2kLink(
        filename=primary.filename or parsed.title or primary.hash,
        size=int(primary.size or 0),
        hash=primary.hash,
        link=primary.uri,
    )
    upsert_resource(
        conn,
        link,
        source_id,
        source_url=source_url,
        title=parsed.title or None,
        description=parsed.description or None,
        preview_images=parsed.preview_images or None,
        ed2k_links=all_uris,
        extract_password=parsed.extract_password or None,
        board_fid=fid,
        board_name=board_name or None,
        forum_id=forum_id,
        import_outcome=import_outcome or "成功：已提取主链",
    )
    return {
        "count": 1,
        "stub": False,
        "hash": primary.hash,
        "link_kind": primary.link_kind,
        "import_outcome": import_outcome or "成功：已提取主链",
    }


def persist_from_html(
    conn: Any,
    html: str,
    *,
    source_url: str,
    tid: int = 0,
    board_fid: int | str = "",
    board_name: str = "",
    preferred_link: str = "both",
) -> dict[str, Any]:
    from parsers.links import parse_thread_dual

    parsed = parse_thread_dual(
        html, tid=tid, preferred_link=preferred_link, board_fid=board_fid
    )  # type: ignore[arg-type]
    return persist_dual_parse(
        conn,
        parsed,
        source_url=source_url,
        board_fid=board_fid,
        board_name=board_name,
    )
