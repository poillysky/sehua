"""DualParseResult → ed2k_resources / resource_sources (aligned with ed2k)."""

from __future__ import annotations

from typing import Any

from db.repository import (
    delete_stub_by_source_url,
    ensure_source,
    import_thread_stub,
    upsert_resource,
)
from parsers.ed2k import Ed2kLink
from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_names import resolve_sub_filename


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
    """Persist one thread parse. Returns {count, stub, hash, link_kind}.

    - 主资源名 title = 帖子标题
    - 子资源名 filename = 【影片名称】/【资源名称】；没有则用主标题（不用 ed2k/dn 链内名）
    - 多磁力/多 ed2k：按 hash 各写一条
    """
    source_id = ensure_source(conn, source_key, source_name, "web")
    fid = str(board_fid) if board_fid not in ("", None) else None

    primary = next((a for a in parsed.assets if a.is_primary), None)
    if primary is None and parsed.assets:
        primary = parsed.assets[0]

    post_title = (parsed.title or "").strip()

    if primary is None:
        count = import_thread_stub(
            conn,
            source_id=source_id,
            source_url=source_url,
            title=post_title or None,
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

    same_kind = [a for a in parsed.assets if a.link_kind == primary.link_kind] or [
        primary
    ]
    seen: set[str] = set()
    uniq: list[ParsedAsset] = []
    for asset in same_kind:
        h = (asset.hash or "").strip().upper()
        if not h or h in seen:
            continue
        seen.add(h)
        uniq.append(asset)
    if not uniq:
        uniq = [primary]

    outcome_msg = import_outcome or (
        f"成功：已提取 {len(uniq)} 条资源" if len(uniq) > 1 else "成功：已提取主链"
    )
    last_hash = primary.hash
    for asset in uniq:
        main_name = post_title or (asset.filename or "").strip() or asset.hash
        sub_name = resolve_sub_filename(
            inner_name=asset.filename,
            title=main_name,
            hash_value=asset.hash,
            link_uri=asset.uri,
            description=asset.description or parsed.description or "",
        )
        link = Ed2kLink(
            filename=sub_name,
            size=int(asset.size or 0),
            hash=asset.hash,
            link=asset.uri,
        )
        upsert_resource(
            conn,
            link,
            source_id,
            source_url=source_url,
            title=main_name,
            description=asset.description or parsed.description or None,
            preview_images=(
                (asset.preview_images or parsed.preview_images or None)[:5]
                if (asset.preview_images or parsed.preview_images)
                else None
            ),
            ed2k_links=[asset.uri],
            extract_password=parsed.extract_password or None,
            board_fid=fid,
            board_name=board_name or None,
            forum_id=forum_id,
            import_outcome=outcome_msg,
        )
        last_hash = asset.hash

    # 真链入库后清掉同帖占位，避免「ed2k + stub」被当成 ×2 合集
    delete_stub_by_source_url(conn, source_url)

    return {
        "count": len(uniq),
        "stub": False,
        "hash": last_hash,
        "link_kind": primary.link_kind,
        "import_outcome": outcome_msg,
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
