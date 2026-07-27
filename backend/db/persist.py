"""DualParseResult → ed2k_resources / resource_sources (aligned with ed2k)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from db.repository import (
    delete_other_resources_by_forum_tid,
    delete_other_resources_by_source_url,
    delete_stub_by_source_url,
    ensure_source,
    import_thread_stub,
    name_row_hash,
    sync_board_meta_by_source_url,
    upsert_resource,
)
from parsers.ed2k import Ed2kLink, coerce_file_size
from parsers.links import DualParseResult, ParsedAsset
from parsers.magnet import parse_capacity_bytes
from parsers.resource_frame import build_resource_frame, format_frame_outcome, warnings_from_frame
from parsers.resource_names import resolve_sub_filename


def _pick_group_primary(assets: list[ParsedAsset]) -> ParsedAsset:
    marked = next((a for a in assets if a.is_primary), None)
    if marked is not None:
        return marked
    return max(assets, key=lambda a: int(a.size or 0))


def _hash_source_urls(conn: Any, hash_values: list[str]) -> dict[str, str] | None:
    """批量查 hash→source_url。无行的 hash 不在 dict；conn 不可用返回 None。"""
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in hash_values:
        h = (raw or "").strip().upper()
        if not h or h in seen:
            continue
        seen.add(h)
        uniq.append(h)
    if not uniq:
        return {}
    try:
        cur_factory = getattr(conn, "cursor", None)
        if cur_factory is None:
            return None
        with conn.cursor() as cur:
            # 等值 ANY 可走 hash 主键；upper(hash)=ANY 会拖成全表扫（40万行可达数秒）
            cur.execute(
                """
                SELECT upper(hash), source_url
                FROM resource_sources
                WHERE hash = ANY(%s)
                """,
                (uniq,),
            )
            rows = cur.fetchall() or []
    except Exception:
        return None
    out: dict[str, str] = {}
    for h, url in rows:
        key = (h or "").strip().upper()
        if key:
            out[key] = (url or "").strip()
    return out


def _hash_source_url(conn: Any, hash_value: str) -> str | None:
    """查 hash 现属帖 URL；查不到返回 ''；conn 无 cursor（单测）返回 None 表示跳过占用检查。"""
    owners = _hash_source_urls(conn, [hash_value])
    if owners is None:
        return None
    h = (hash_value or "").strip().upper()
    if not h:
        return ""
    return owners.get(h, "")


def _pick_writable_primary(
    conn: Any,
    members: list[ParsedAsset],
    source_url: str,
    *,
    resource_name: str = "",
    forum_id: str = "",
) -> ParsedAsset:
    """优先空闲/本帖 hash；全部被其它帖占用时用帖+资源名合成行键（真链仍进 ed2k_links）。

    大包同名多链：分块批量查，一有可用 hash 即返回（禁止对 900+ 链逐条往返）。
    """
    url = (source_url or "").strip()
    ordered: list[ParsedAsset] = []
    marked = next((a for a in members if a.is_primary), None)
    if marked is not None:
        ordered.append(marked)
    for asset in members:
        if asset is not marked:
            ordered.append(asset)

    free: list[ParsedAsset] = []
    same: list[ParsedAsset] = []
    chunk_size = 64
    for i in range(0, len(ordered), chunk_size):
        chunk = ordered[i : i + chunk_size]
        owners = _hash_source_urls(conn, [a.hash or "" for a in chunk])
        if owners is None:
            return _pick_group_primary(members)
        for asset in chunk:
            h = (asset.hash or "").strip().upper()
            if not h:
                continue
            if h not in owners:
                free.append(asset)
            elif owners[h] == url:
                same.append(asset)
        pool = free or same
        if pool:
            return _pick_group_primary(pool)

    base = _pick_group_primary(members)
    syn = name_row_hash(
        url,
        resource_name or base.filename or base.hash or "",
        forum_id=forum_id,
    )
    return replace(base, hash=syn, is_primary=True)


def _is_truncated_resource_name(short: str, long: str) -> bool:
    """短名是长名前缀（附件/切段常见脏截断）→ 应并入长名。"""
    s = (short or "").strip()
    l = (long or "").strip()
    if not s or not l or s == l or len(s) >= len(l):
        return False
    if l.startswith(s):
        return True
    return l.replace(" ", "").startswith(s.replace(" ", ""))


def _merge_truncated_name_groups(
    groups: list[tuple[str, ParsedAsset, list[ParsedAsset]]],
) -> list[tuple[str, ParsedAsset, list[ParsedAsset]]]:
    """两名时若一者为另一前缀，并入长名；多名时把截断短名吸进唯一匹配的长名。"""
    if len(groups) <= 1:
        return groups
    if len(groups) == 2:
        (n0, _h0, m0), (n1, _h1, m1) = groups
        if _is_truncated_resource_name(n0, n1):
            members = m1 + m0
            return [(n1, _pick_group_primary(members), members)]
        if _is_truncated_resource_name(n1, n0):
            members = m0 + m1
            return [(n0, _pick_group_primary(members), members)]
        return groups

    # 多名：短前缀名且仅匹配一个长名 → 吸收
    by_name = {n: list(m) for n, _h, m in groups}
    names = list(by_name.keys())
    absorb_into: dict[str, str] = {}
    for short in names:
        longs = [
            long
            for long in names
            if long != short and _is_truncated_resource_name(short, long)
        ]
        if len(longs) == 1:
            absorb_into[short] = longs[0]
    if not absorb_into:
        return groups
    for short, long in absorb_into.items():
        if short in by_name and long in by_name:
            by_name[long].extend(by_name.pop(short))
    out: list[tuple[str, ParsedAsset, list[ParsedAsset]]] = []
    seen: set[str] = set()
    for n, _h, _m in groups:
        key = absorb_into.get(n, n)
        if key in seen or key not in by_name:
            continue
        seen.add(key)
        members = by_name[key]
        out.append((key, _pick_group_primary(members), members))
    return out


def _group_assets_by_resource_name(
    uniq: list[ParsedAsset],
    *,
    post_title: str,
    parsed: DualParseResult,
) -> list[tuple[str, ParsedAsset, list[ParsedAsset]]]:
    """按资源名称分组；返回 [(resource_name, primary, members), ...]。"""
    groups: dict[str, list[ParsedAsset]] = {}
    order: list[str] = []
    for asset in uniq:
        main_name = post_title or (asset.filename or "").strip() or asset.hash
        sub_name = resolve_sub_filename(
            inner_name=asset.filename,
            title=main_name,
            hash_value=asset.hash,
            link_uri=asset.uri,
            description=asset.description or parsed.description or "",
        )
        key = (sub_name or main_name or asset.hash or "").strip() or (asset.hash or "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(asset)
    out: list[tuple[str, ParsedAsset, list[ParsedAsset]]] = []
    for key in order:
        members = groups[key]
        out.append((key, _pick_group_primary(members), members))
    return out


def _sanitize_stub_outcome(tip: str | None) -> str:
    """占位入库不得以「成功」开头，避免假成功。"""
    t = (tip or "").strip() or "无下载链 · 占位入库"
    if t.startswith("成功"):
        rest = t[len("成功") :].lstrip("：: ·")
        t = f"占位：{rest}" if rest else "占位入库"
    return t


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
    replace_thread_assets: bool = False,
) -> dict[str, Any]:
    """Persist one thread parse. Returns {count, stub, hash, link_kind}.

    处理记录按帖（一帖一次调用）；入库按资源名称：
    - title = 帖子标题（帖维，同帖可相同）
    - filename = 【影片名称】/【资源名称】（入库维；无则用帖标题；不用 dn/链内名）
    - 同一资源名下多条链合并为 1 行，链写入 ed2k_links
    - 不同资源名各写 1 行
    - replace_thread_assets：重爬时删掉同帖 URL 下本次未保留的旧真链
    """
    from parsers.thread_gates import coalesce_thread_title, title_recognizable

    primary = next((a for a in parsed.assets if a.is_primary), None)
    if primary is None and parsed.assets:
        primary = parsed.assets[0]

    # 过滤「提示信息」等系统伪标题，避免占位/主资源名脏数据
    post_title = coalesce_thread_title(parsed.title) or ""
    if post_title and parsed.title != post_title:
        parsed.title = post_title

    if primary is None and not title_recognizable(post_title):
        return {
            "count": 0,
            "stub": False,
            "hash": None,
            "link_kind": "skipped_tip_title",
            "import_outcome": "伪标题拒绝占位",
        }

    source_id = ensure_source(conn, source_key, source_name, "web", commit=False)
    fid = str(board_fid) if board_fid not in ("", None) else None

    if primary is None:
        stub_tip = _sanitize_stub_outcome(import_outcome)
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
            import_outcome=stub_tip,
        )
        return {
            "count": count,
            "stub": True,
            "hash": None,
            "link_kind": "stub" if count else "failed",
            "import_outcome": stub_tip,
            "verdict": "stub",
            "shape": "F",
            "kind": "no_link",
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

    raw_groups = _group_assets_by_resource_name(
        uniq, post_title=post_title, parsed=parsed
    )
    named_groups = _merge_truncated_name_groups(raw_groups)
    truncated_merged = len(named_groups) < len(raw_groups)

    frame = build_resource_frame(
        parsed,
        named_groups=named_groups,
        had_attachments=bool(getattr(parsed, "had_attachments", False)),
        truncated_merged=truncated_merged,
        layout=str(getattr(parsed, "layout", "") or ""),
        post_title=post_title,
    )

    # 条数 = 资源名称数（入库维），不是磁力数
    tip = (import_outcome or "").strip()
    if len(frame.rows) > 1:
        base_tip = f"成功：已提取 {len(frame.rows)} 条资源"
    elif tip:
        base_tip = tip
    else:
        base_tip = "成功：已提取主链"
    outcome_msg = format_frame_outcome(base_tip, frame)
    shape_tags = list(frame.verdict.tags)
    shape_warnings = warnings_from_frame(frame)
    last_hash = primary.hash
    kept: list[str] = []

    for row in frame.rows:
        head = _pick_writable_primary(
            conn,
            row.members,
            source_url,
            resource_name=row.filename,
            forum_id=forum_id,
        )
        main_name = post_title or row.filename or head.hash
        uris = list(row.links)
        if not uris and head.uri:
            uris = [head.uri]
        primary_uri = next(
            (u for u in uris if u),
            (head.uri or "").strip(),
        )
        previews = list(row.previews[:5])
        desc = head.description or parsed.description or ""
        for asset in row.members:
            if asset.description:
                desc = asset.description
                break

        size = int(row.size or 0)
        if not size:
            # 文案容量优先于链内 xl（合集【23V 55GB】勿被残缺 xl 盖成几十 MB）
            for text in (
                desc,
                row.filename,
                main_name,
                parsed.description or "",
                post_title,
            ):
                size = parse_capacity_bytes(text)
                if size:
                    break
            meta = getattr(parsed, "metadata", None) or {}
            if not size and isinstance(meta, dict):
                for key in ("资源大小", "影片大小", "文件大小", "影片容量"):
                    size = parse_capacity_bytes(str(meta.get(key) or ""))
                    if size:
                        break
        if not size:
            for asset in row.members:
                size = max(size, int(asset.size or 0))
        size = coerce_file_size(size, uris)

        link = Ed2kLink(
            filename=row.filename,
            size=size,
            hash=head.hash,
            link=primary_uri,
        )
        wrote = upsert_resource(
            conn,
            link,
            source_id,
            source_url=source_url,
            title=main_name,
            description=desc or None,
            preview_images=(previews if previews else None),
            ed2k_links=uris,
            extract_password=parsed.extract_password or None,
            board_fid=fid,
            board_name=board_name or None,
            forum_id=forum_id,
            import_outcome=outcome_msg,
            parse_tags=shape_tags,
            parse_warnings=shape_warnings,
            commit=False,
        )
        if wrote and head.hash:
            kept.append(str(head.hash).strip().upper())
            last_hash = head.hash

    purged = 0
    if replace_thread_assets and kept:
        # 重爬：同帖只保留本次实际写入的 primary hash
        purged = delete_other_resources_by_source_url(
            conn,
            source_url,
            kept,
            commit=False,
        )
        # 2048 镜像域名：同 forum+tid 的其它 URL 一并清掉，避免处理记录出现两行同帖
        from db.queue import tid_from_url

        tid_i = tid_from_url(source_url) or 0
        if (forum_id or "").strip() == "2048" and tid_i:
            purged += delete_other_resources_by_forum_tid(
                conn,
                forum_id="2048",
                tid=int(tid_i),
                keep_hashes=kept,
                keep_source_url=source_url,
                commit=False,
            )
    # 同帖旧 hash 行也回写板块（未开启替换时仍修正脏名）
    sync_board_meta_by_source_url(
        conn,
        source_url,
        board_fid=fid,
        board_name=board_name or None,
        forum_id=forum_id,
        commit=False,
    )
    # 真链入库后清掉同帖占位，避免「ed2k + stub」被当成 ×2 合集
    delete_stub_by_source_url(conn, source_url, commit=False)
    try:
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise

    return {
        "count": len(kept),
        "stub": False,
        "hash": last_hash,
        "link_kind": primary.link_kind,
        "import_outcome": outcome_msg,
        "purged": purged,
        "shape": frame.spec.shape,
        "kind": frame.spec.kind,
        "verdict": frame.verdict.status,
        "parse_tags": shape_tags,
        "parse_warnings": shape_warnings,
        "shape_metrics": dict(frame.verdict.metrics),
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
