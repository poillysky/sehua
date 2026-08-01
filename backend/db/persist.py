"""DualParseResult → ed2k_resources / resource_sources (aligned with ed2k)."""

from __future__ import annotations

import html
import re
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
    thread_stub_hash,
    upsert_resource,
)
from parsers.ed2k import Ed2kLink, coerce_file_size
from parsers.links import DualParseResult, ParsedAsset
from parsers.magnet import parse_capacity_bytes
from parsers.resource_frame import build_resource_frame, format_frame_outcome, warnings_from_frame
from parsers.resource_names import resolve_sub_filename


def _norm_uri_dedupe_key(uri: str) -> str:
    """同链仅实体编码 / 空白差异（&nbsp;、全角空格）时视为同一 URI。"""
    text = html.unescape((uri or "").strip())
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text


_NAME_PUNCT_TRANS = str.maketrans(
    {
        "：": ":",
        "︰": ":",
        "＆": "&",
        "\u3000": " ",
    }
)


def _strip_html_noise(text: str) -> str:
    """剥完整/残缺标签与变体选择符（Discuz 常把 ❤/❤️、<font 拆进片名）。"""
    t = html.unescape(text or "")
    t = re.sub(r"<[^>]*>", " ", t)
    # 未闭合残片：`<font size="2` / `</font`
    t = re.sub(r"</?[A-Za-z][^<\n]*", " ", t)
    t = t.replace("\ufe0e", "").replace("\ufe0f", "")
    return t


def _norm_resource_name_key(name: str) -> str:
    """分组键：解实体 + 去 HTML/VS + 全角冒号/＆ 归一，避免假多资源名。"""
    text = _strip_html_noise(name).translate(_NAME_PUNCT_TRANS)
    return re.sub(r"\s+", " ", text).strip()


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


def _normalize_resource_name_key(name: str) -> str:
    """合并用：去 HTML/警告 emoji/变体选择符，避免 ⚠ vs ⚠️、❤ vs ❤️ 切成双名。"""
    t = _strip_html_noise(name)
    t = re.sub(r"[⚠⚠︎]", "", t)
    t = re.sub(r"\s+", "", t)
    return t


def _names_emoji_equivalent(a: str, b: str) -> bool:
    ka = _normalize_resource_name_key(a)
    kb = _normalize_resource_name_key(b)
    return bool(ka) and ka == kb and (a or "").strip() != (b or "").strip()


def _prefer_clean_display_name(a: str, b: str) -> str:
    """两名等价时优先无 HTML/残片、无 VS 噪音的展示名。"""
    a0 = (a or "").strip()
    b0 = (b or "").strip()
    if not a0:
        return b0
    if not b0:
        return a0
    score = lambda s: (
        0 if ("<" in s or ">" in s) else 1,
        0 if "\ufe0f" in s else 1,
        len(_strip_html_noise(s).strip()),
    )
    return a0 if score(a0) >= score(b0) else b0


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
        # 仅警告符 / 爱心 VS / HTML 残片差异 → 并入干净展示名
        if _names_emoji_equivalent(n0, n1):
            keep = _prefer_clean_display_name(n0, n1)
            members = m0 + m1
            return [(keep, _pick_group_primary(members), members)]
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


def _post_level_name_label_count(parsed: DualParseResult) -> int:
    """帖级（非逐块）【资源名称】/【影片名称】标签数——人一眼判单/多的硬信号。"""
    from parsers.content import iter_subresource_title_spans
    from parsers.structure_cards import name_values_from_cards, parse_structure_cards

    parts: list[str] = []
    desc = (getattr(parsed, "description", None) or "").strip()
    if desc:
        parts.append(desc)
    meta = getattr(parsed, "metadata", None) or {}
    for key, val in meta.items():
        k = (key or "").strip()
        v = (val or "").strip()
        if not k or not v:
            continue
        if any(x in k for x in ("名称", "片名", "標題", "标题")):
            parts.append(f"【{k}】：{v}")
    blob = "\n".join(parts)
    if not blob:
        return 0
    spans = iter_subresource_title_spans(blob)
    if spans:
        return len(spans)
    return len(name_values_from_cards(parse_structure_cards(blob)))


def _collapse_groups_to_single(
    groups: list[tuple[str, ParsedAsset, list[ParsedAsset]]],
) -> list[tuple[str, ParsedAsset, list[ParsedAsset]]]:
    if len(groups) <= 1:
        return groups
    members: list[ParsedAsset] = []
    keep = (groups[0][0] or "").strip()
    for name, _head, mem in groups:
        members.extend(mem)
        keep = _prefer_clean_display_name(keep, name)
    return [(keep, _pick_group_primary(members), members)]


def _group_assets_by_resource_name(
    uniq: list[ParsedAsset],
    *,
    post_title: str,
    parsed: DualParseResult,
) -> list[tuple[str, ParsedAsset, list[ParsedAsset]]]:
    """按资源名称分组；返回 [(resource_name, primary, members), ...]。"""
    groups: dict[str, list[ParsedAsset]] = {}
    order: list[str] = []
    display_by_key: dict[str, str] = {}
    for asset in uniq:
        main_name = post_title or (asset.filename or "").strip() or asset.hash
        sub_name = resolve_sub_filename(
            inner_name=asset.filename,
            title=main_name,
            hash_value=asset.hash,
            link_uri=asset.uri,
            description=asset.description or parsed.description or "",
        )
        display = (sub_name or main_name or asset.hash or "").strip() or (asset.hash or "")
        key = _norm_resource_name_key(display) or display
        if key not in groups:
            groups[key] = []
            order.append(key)
            # 保留首次展示名（可能含全角冒号）
            display_by_key[key] = display
        groups[key].append(asset)
    out: list[tuple[str, ParsedAsset, list[ParsedAsset]]] = []
    for key in order:
        members = groups[key]
        out.append((display_by_key.get(key, key), _pick_group_primary(members), members))
    return out


def _sanitize_stub_outcome(tip: str | None) -> str:
    """占位入库不得以「成功」开头，避免假成功。"""
    t = (tip or "").strip() or "无下载链 · 占位入库"
    if t.startswith("成功"):
        rest = t[len("成功") :].lstrip("：: ·")
        t = f"占位：{rest}" if rest else "占位入库"
    return t


def build_parse_frame(
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> Any | None:
    """按入库相同规则定型填槽（不写库）。无主链返回 None。"""
    from parsers.thread_gates import coalesce_thread_title

    primary = next((a for a in parsed.assets if a.is_primary), None)
    if primary is None and parsed.assets:
        primary = parsed.assets[0]
    if primary is None:
        return None

    title = (post_title or "").strip() or (coalesce_thread_title(parsed.title) or "")
    # magnet+ed2k 并存时两种都入库/计数（附件解压常见双列表）；仅无 115 分享时才用分享链
    candidates = [
        a
        for a in (parsed.assets or [])
        if (a.link_kind or "") in {"magnet", "ed2k"}
    ]
    if not candidates:
        candidates = [
            a
            for a in (parsed.assets or [])
            if (a.link_kind or "") == "115share"
        ] or [primary]
    # 按 URI 去重：同 hash 不同文件名仍算多份（配额对照）；完全相同 URI（含仅实体编码差异）才并掉
    seen: set[str] = set()
    uniq: list[ParsedAsset] = []
    for asset in candidates:
        u = _norm_uri_dedupe_key(asset.uri or "")
        h = (asset.hash or "").strip().upper()
        key = u or h
        if not key or key in seen:
            continue
        seen.add(key)
        uniq.append(asset)
    if not uniq:
        uniq = [primary]

    raw_groups = _group_assets_by_resource_name(
        uniq, post_title=title, parsed=parsed
    )
    named_groups = _merge_truncated_name_groups(raw_groups)
    # 人一眼：帖级只有 1 个名称标签 → 单资源多链；禁止脏文件名/爱心 VS 拆成多资源
    if len(named_groups) > 1 and _post_level_name_label_count(parsed) == 1:
        named_groups = _collapse_groups_to_single(named_groups)
    truncated_merged = len(named_groups) < len(raw_groups)
    return build_resource_frame(
        parsed,
        named_groups=named_groups,
        had_attachments=bool(getattr(parsed, "had_attachments", False)),
        truncated_merged=truncated_merged,
        layout=str(getattr(parsed, "layout", "") or ""),
        post_title=title,
    )


def preview_frame_outcome(
    parsed: DualParseResult,
    *,
    import_outcome: str = "",
    post_title: str = "",
) -> str:
    """试算入库 outcome（含不合格：*），用于正文有链但验收不过时决定是否再下附件。"""
    from parsers.thread_gates import coalesce_thread_title

    title = (post_title or "").strip() or (coalesce_thread_title(parsed.title) or "")
    frame = build_parse_frame(parsed, post_title=title)
    if frame is None:
        return ""
    tip = (import_outcome or "").strip()
    if len(frame.rows) > 1:
        base_tip = f"成功：已提取 {len(frame.rows)} 条资源"
    elif tip:
        base_tip = tip
    else:
        base_tip = "成功：已提取主链"
    return format_frame_outcome(base_tip, frame)


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
    - replace_thread_assets：重爬时删掉同帖 URL 下本次未保留的旧真链；
      改判占位时先写 stub 再清旧真链，使帖子离开「不合格」明细
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
        purged = 0
        stub_hash = thread_stub_hash(source_url)
        if replace_thread_assets:
            # 先写占位再清旧真链：不合格重爬→附件无权等占位时，须离开不合格明细
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
                force=True,
                commit=False,
            )
            purged = delete_other_resources_by_source_url(
                conn,
                source_url,
                [stub_hash],
                commit=False,
            )
            from db.queue import tid_from_url

            tid_i = tid_from_url(source_url) or 0
            if (forum_id or "").strip() == "2048" and tid_i:
                purged += delete_other_resources_by_forum_tid(
                    conn,
                    forum_id="2048",
                    tid=int(tid_i),
                    keep_hashes=[stub_hash],
                    keep_source_url=source_url,
                    commit=False,
                )
            try:
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
        else:
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
            "hash": stub_hash if count else None,
            "link_kind": "stub" if count else "failed",
            "import_outcome": stub_tip,
            "verdict": "stub",
            "shape": "F",
            "kind": "no_link",
            "purged": purged,
        }

    frame = build_parse_frame(parsed, post_title=post_title)
    if frame is None:
        stub_tip = _sanitize_stub_outcome(import_outcome)
        return {
            "count": 0,
            "stub": False,
            "hash": None,
            "link_kind": "failed",
            "import_outcome": stub_tip or "无主链",
            "verdict": "failed",
        }

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
        from parsers.content import PREVIEW_IMAGE_LIMIT

        previews = list(row.previews[:PREVIEW_IMAGE_LIMIT])
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
