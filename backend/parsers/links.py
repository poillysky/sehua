"""Dual magnet + ed2k (+ 115 分享码) link extraction facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from parsers.content import (
    PREVIEW_IMAGE_LIMIT,
    ThreadContent,
    attachment_corpus_has_target_links,
    build_structured_description,
    extract_blockcode_text,
    extract_link_corpus_html,
    extract_subresource_blocks,
    extract_subresource_blocks_ex,
    harvest_extract_password,
    parse_thread_content,
)
from parsers.ed2k import Ed2kLink, parse_ed2k_text, pick_primary_ed2k
from parsers.magnet import MagnetLink, parse_magnet_text, pick_primary_magnet
from parsers.share115 import Share115Link, parse_115_share_text, pick_primary_115_share

LinkKind = Literal["magnet", "ed2k", "both", "none"]
AssetKind = Literal["magnet", "ed2k", "115share"]
PrimaryKind = Literal["magnet", "ed2k", "115share", "none"]


@dataclass(slots=True)
class ParsedAsset:
    link_kind: AssetKind
    hash: str
    filename: str
    size: int
    uri: str
    is_primary: bool = False
    access_code: str = ""
    preview_images: list[str] = field(default_factory=list)
    # 合集子资源块描述（名称/大小/格式/说明）；空则入库用帖级 description
    description: str = ""


@dataclass(slots=True)
class DualParseResult:
    tid: int
    title: str
    description: str
    metadata: dict[str, str]
    preview_images: list[str]
    extract_password: str
    magnets: list[MagnetLink] = field(default_factory=list)
    ed2k_links: list[Ed2kLink] = field(default_factory=list)
    share115_links: list[Share115Link] = field(default_factory=list)
    assets: list[ParsedAsset] = field(default_factory=list)
    primary_link_kind: PrimaryKind = "none"
    # 切块布局：no_subtitle / names_then_links / title_then_magnet / magnet_then_title
    layout: str = ""
    # 流水线：本帖是否注入过附件文本
    had_attachments: bool = False
    # 帖内下载向链总数（含非入库残链/HTTP；配额旁证，不计入库）
    quota_link_count: int = 0
    # 兼容旧字段：HTTP 媒体直链数
    http_media_count: int = 0
    # 帖面附件文件名（含未下载的）；供额度对照「96v.txt」等口径
    attachment_names: list[str] = field(default_factory=list)

    @property
    def search_string(self) -> str:
        parts = [self.title, self.description, self.extract_password]
        for asset in self.assets:
            parts.append(asset.filename)
        return " ".join(p for p in parts if p).strip()


def _build_description(content: ThreadContent, board_fid: str | int | None = None) -> str:
    """详情描述：按板块结构卡片字段白名单。"""
    return build_structured_description(
        content.metadata,
        extract_password=content.extract_password,
        title=content.title,
        board_fid=board_fid,
    )


def parse_links_from_text(text: str) -> tuple[list[MagnetLink], list[Ed2kLink]]:
    return parse_magnet_text(text), parse_ed2k_text(text)


def build_assets(
    magnets: list[MagnetLink],
    ed2k_links: list[Ed2kLink],
    preferred: LinkKind = "both",
    share115_links: list[Share115Link] | None = None,
) -> tuple[list[ParsedAsset], PrimaryKind]:
    """Merge link types; choose one primary according to board preference.

    115 分享仅在无 magnet/ed2k 时作为主链入库。
    """
    assets: list[ParsedAsset] = []
    shares = share115_links or []

    primary_magnet = pick_primary_magnet(magnets) if magnets else None
    primary_ed2k = pick_primary_ed2k(ed2k_links) if ed2k_links else None
    primary_115 = pick_primary_115_share(shares) if shares else None

    for link in magnets:
        assets.append(
            ParsedAsset(
                link_kind="magnet",
                hash=link.infohash,
                filename=link.filename,
                size=link.size,
                uri=link.link,
                is_primary=False,
            )
        )
    for link in ed2k_links:
        assets.append(
            ParsedAsset(
                link_kind="ed2k",
                hash=link.hash,
                # 子资源名用帖内真名；链内 filename 仅保留在 uri 里
                filename=(link.display_name or "").strip(),
                size=link.size,
                uri=link.link,
                is_primary=False,
            )
        )
    for link in shares:
        assets.append(
            ParsedAsset(
                link_kind="115share",
                hash=link.hash,
                filename=link.filename,
                size=0,
                uri=link.url,
                is_primary=False,
                access_code=link.password or "",
            )
        )

    primary_kind: PrimaryKind = "none"
    if preferred == "magnet":
        if primary_magnet:
            primary_kind = "magnet"
        elif primary_ed2k:
            primary_kind = "ed2k"
        elif primary_115:
            primary_kind = "115share"
    elif preferred == "ed2k":
        if primary_ed2k:
            primary_kind = "ed2k"
        elif primary_magnet:
            primary_kind = "magnet"
        elif primary_115:
            primary_kind = "115share"
    else:
        if primary_magnet:
            primary_kind = "magnet"
        elif primary_ed2k:
            primary_kind = "ed2k"
        elif primary_115:
            primary_kind = "115share"

    if primary_kind == "magnet" and primary_magnet:
        for asset in assets:
            if asset.link_kind == "magnet" and asset.hash == primary_magnet.infohash:
                asset.is_primary = True
                break
    elif primary_kind == "ed2k" and primary_ed2k:
        for asset in assets:
            if asset.link_kind == "ed2k" and asset.hash == primary_ed2k.hash:
                asset.is_primary = True
                break
    elif primary_kind == "115share" and primary_115:
        for asset in assets:
            if asset.link_kind == "115share" and asset.hash == primary_115.hash:
                asset.is_primary = True
                break

    return assets, primary_kind


def parse_thread_dual(
    html: str,
    *,
    tid: int = 0,
    preferred_link: LinkKind = "both",
    extra_text: str = "",
    base_url: str = "",
    board_fid: str | int | None = None,
) -> DualParseResult:
    """
    Full dual parse: HTML → 先定资源名（单/多）→ 再定楼层抽链 → 切块挂链 → 块内卡片 → ParsedAsset。

    preferred_link: board policy — 'magnet' | 'ed2k' | 'both'
    extra_text: 附件解析出的文本（txt/zip/rar 内链或 torrent→magnet）并入语料
    board_fid: 用于按板块结构卡片筛选描述字段

    顺序：一楼名称标签 0～1=单资源（可扫楼主多楼补链），≥2=多资源（只一楼）。
    认 magnet/ed2k 之前已有资源名结论；路人回帖不参与。
    """
    content = parse_thread_content(html, tid=tid, base_url=base_url)
    # 2048 等板：繁简标签归一、丢掉裸 hash/残片种子名，便于片名与大小精准入库
    if board_fid is not None:
        from parsers.content import normalize_metadata_for_board

        content.metadata = normalize_metadata_for_board(content.metadata, board_fid)

    # ① 先有资源名称结论（一楼标签数）→ ② 再选抽链楼层 → ③ 才认 magnet/ed2k
    from parsers.content import should_scan_lz_multi_floor

    multi_floor = should_scan_lz_multi_floor(html)  # 名称≤1 才扫楼主多楼
    link_html = extract_link_corpus_html(html, multi_floor=multi_floor)
    link_block = extract_blockcode_text(link_html) if link_html else ""
    # 附件已含目标链：抽链不再并入正文 plain/blockcode（避免正文样例链污染）
    if attachment_corpus_has_target_links(html):
        corpus = "\n".join(
            part
            for part in (link_block, link_html, content.title, extra_text or "")
            if part
        )
    else:
        # 多资源：正文 plain 仍可能来自一楼；链语料已按 multi_floor 收窄
        corpus = "\n".join(
            part
            for part in (
                link_block,
                link_html,
                content.blockcode_text,
                content.plain_text,
                content.title,
                extra_text or "",
            )
            if part
        )

    magnets, ed2k_links = parse_links_from_text(corpus)
    share115_links = parse_115_share_text(corpus, title=content.title)
    assets, primary_kind = build_assets(
        magnets,
        ed2k_links,
        preferred=preferred_link,
        share115_links=share115_links,
    )
    # 子资源：按子标题切段（无子标题则整帖用帖标题）；
    # 一段内多链全部入库；连续名称后接连续链接则 1:1
    hashes = [a.hash for a in assets if a.link_kind in {"magnet", "ed2k"} and a.hash]
    layout = ""
    if hashes:
        # 附件主导的大合集：正文几乎无子标题时跳过切块（避免对 50 万字×千链做 O(n) 装配）
        _PACK_ATTACH_FAST = 48
        skip_blocks = False
        if len(hashes) >= _PACK_ATTACH_FAST and (
            attachment_corpus_has_target_links(html) or len(extra_text or "") >= 24_000
        ):
            from parsers.content import (
                extract_first_postmessage_html,
                iter_subresource_title_spans,
            )

            body_only = extract_first_postmessage_html(html) or ""
            body_titles = iter_subresource_title_spans(body_only)
            if len(body_titles) <= 1:
                skip_blocks = True
                layout = "pack_attach_fast"
                pack_name = (content.title or "").strip()
                if pack_name:
                    from parsers.resource_names import (
                        clip_subresource_display_name,
                        is_dirty_filename,
                        is_hard_dirty_filename,
                    )

                    cleaned = clip_subresource_display_name(pack_name) or pack_name
                    if cleaned and not is_dirty_filename(cleaned) and not is_hard_dirty_filename(
                        cleaned
                    ):
                        for asset in assets:
                            if asset.link_kind in {"magnet", "ed2k"}:
                                asset.filename = cleaned[:255]
                # 帖级预览挂到主链资产（其余名共享由 persist/frame 回落）
                previews = list(content.preview_images or [])[:PREVIEW_IMAGE_LIMIT]
                if previews:
                    for asset in assets:
                        if asset.is_primary:
                            asset.preview_images = previews
                            break

        if not skip_blocks:
            blocks, layout = extract_subresource_blocks_ex(
                html,
                hashes,
                base_url=base_url,
                limit_per=PREVIEW_IMAGE_LIMIT,
                fallback_title=content.title or "",
                board_fid=board_fid,
            )
            if blocks:
                # 同 hash 可能对应多条不同文件名 URI（配额份）；按 URI 保活，勿 hash 字典压成一条
                from collections import defaultdict

                by_hash_q: dict[str, list[ParsedAsset]] = defaultdict(list)
                for a in assets:
                    h = (a.hash or "").strip().upper()
                    if h:
                        by_hash_q[h].append(a)
                ordered: list[ParsedAsset] = []
                for b in blocks:
                    q = by_hash_q.get((b.infohash or "").strip().upper()) or []
                    asset = q.pop(0) if q else None
                    if not asset:
                        continue
                    if b.title:
                        from parsers.resource_names import (
                            clip_subresource_display_name,
                            is_decoration_only_filename,
                            is_dirty_filename,
                            is_hard_dirty_filename,
                            is_weak_subresource_name,
                            subtitle_from_description,
                        )

                        if is_hard_dirty_filename(b.title) or is_decoration_only_filename(
                            b.title
                        ):
                            cleaned = ""
                        else:
                            cleaned = clip_subresource_display_name(b.title)
                        post_title = (content.title or "").strip()
                        if (
                            cleaned
                            and not is_dirty_filename(cleaned)
                            and not is_weak_subresource_name(
                                cleaned, post_title=post_title, hash_value=asset.hash or ""
                            )
                        ):
                            asset.filename = cleaned[:255]
                        else:
                            # 切段名脏/弱：先从块 description 救真名，再回落帖标题
                            salvaged = subtitle_from_description(b.description or "")
                            if (
                                salvaged
                                and not is_dirty_filename(salvaged)
                                and not is_hard_dirty_filename(salvaged)
                                and not is_weak_subresource_name(
                                    salvaged,
                                    post_title=post_title,
                                    hash_value=asset.hash or "",
                                )
                            ):
                                asset.filename = salvaged[:255]
                            elif post_title:
                                # 切段名脏：回退帖标题；标题字段可含【影片名称】原文，资源名仍 unwrap
                                from parsers.resource_names import unwrap_subject_film_title

                                fb = (
                                    clip_subresource_display_name(
                                        unwrap_subject_film_title(post_title) or post_title
                                    )
                                    or unwrap_subject_film_title(post_title)
                                    or post_title
                                )
                                if (
                                    fb
                                    and not is_dirty_filename(fb)
                                    and not is_hard_dirty_filename(fb)
                                ):
                                    asset.filename = fb[:255]
                    if b.size and b.size > 0:
                        asset.size = int(b.size)
                    if b.preview_images:
                        asset.preview_images = list(b.preview_images)
                    if b.description:
                        asset.description = b.description
                    asset.is_primary = False
                    ordered.append(asset)
                if ordered:
                    ordered[0].is_primary = True
                    # 切段未覆盖的链仍保留（同 hash 不同文件名也要留，防配额漏计）
                    kept_uris = {
                        (a.uri or "").strip() for a in ordered if (a.uri or "").strip()
                    }
                    for asset in assets:
                        u = (asset.uri or "").strip()
                        if not u or u in kept_uris:
                            continue
                        if asset.link_kind not in {"magnet", "ed2k"}:
                            continue
                        asset.is_primary = False
                        ordered.append(asset)
                        kept_uris.add(u)
                    assets = ordered
                    primary_kind = ordered[0].link_kind  # type: ignore[assignment]

                # 帖级 meta/desc：单资源名用唯一块卡片；多资源明细在 asset.description
                name_keys = {
                    (b.title or "").strip() for b in blocks if (b.title or "").strip()
                }
                if len(name_keys) <= 1 and blocks[0].metadata:
                    # 块 meta 为主；保留一楼已有而块内缺失的键（切段名/密码等）
                    merged = dict(content.metadata or {})
                    merged.update(blocks[0].metadata)
                    if blocks[0].title:
                        if "资源名称" not in merged and "影片名称" not in merged:
                            merged["资源名称"] = blocks[0].title
                    content.metadata = merged
                    block_pwd = harvest_extract_password("", metadata=content.metadata)
                    if block_pwd:
                        content.extract_password = block_pwd
                elif len(name_keys) > 1:
                    # 多资源：避免整帖卡片名盖住分块
                    content.metadata = {}
    extract_password = content.extract_password
    # 多源再收一遍：一楼/块 meta + 楼主语料 + 附件（密码常写在文末或附件里）
    harvested = harvest_extract_password(
        content.plain_text or "",
        content.blockcode_text or "",
        link_html or "",
        extra_text or "",
        metadata=content.metadata,
    )
    if harvested:
        extract_password = harvested
    elif not extract_password and content.metadata:
        extract_password = harvest_extract_password("", metadata=content.metadata) or ""
    if primary_kind == "115share":
        primary = next((a for a in assets if a.is_primary), None)
        if primary and primary.access_code:
            extract_password = primary.access_code

    # 描述在最终密码确定后再拼（附件语料里的解压密码也要进描述）
    # 单资源：优先块描述（切段名准），再补密码；多资源：明细在 asset.description
    primary_asset = next((a for a in assets if a.is_primary), None)
    single_name = (
        len(
            {
                (a.filename or "").strip()
                for a in assets
                if a.link_kind in {"magnet", "ed2k"} and (a.filename or "").strip()
            }
        )
        <= 1
    )
    if primary_asset and (primary_asset.description or "").strip() and (
        not content.metadata or single_name
    ):
        description = primary_asset.description
        if extract_password and "解压密码" not in description and "解壓密碼" not in description:
            description = (
                description.rstrip() + f"\n【解压密码】：{extract_password}"
            ).strip()
    else:
        description = build_structured_description(
            content.metadata,
            extract_password=extract_password,
            title=content.title,
            board_fid=board_fid,
        )

    from parsers.content import extract_attachment_inject_text
    from parsers.resource_frame import count_http_host_media_links, count_post_quota_links

    # 额度只认正文 plain + 附件文本（出现次数、不去重；残缺 ed2k/magnet 行也计）。
    # 有附件目标链时只计附件，避免正文样例链再叠一层；绝不回落整页 HTML。
    # pipeline 常 inject 后未传 extra_text：从 postmessage_attach* 回取附件语料。
    body_plain = (content.plain_text or "").strip()
    attach_text = (extra_text or "").strip() or extract_attachment_inject_text(html)
    attach_has_target = bool(attach_text) and (
        "magnet:" in attach_text.lower()
        or "ed2k://" in attach_text.lower()
        or attachment_corpus_has_target_links(html)
    )
    if attach_text and attach_has_target:
        quota_src = attach_text
    elif body_plain and attach_text:
        quota_src = f"{body_plain}\n{attach_text}"
    else:
        quota_src = body_plain or attach_text
    quota_n = count_post_quota_links(quota_src) if quota_src else 0
    http_n = count_http_host_media_links(quota_src) if quota_src else 0

    att_names: list[str] = []
    try:
        from parsers.attachments import extract_download_attachments

        for item in extract_download_attachments(base_url or "", html):
            name = (item.name or "").strip()
            if name and name not in att_names:
                att_names.append(name)
    except Exception:
        att_names = []

    return DualParseResult(
        tid=content.tid or tid,
        title=content.title,
        description=description,
        metadata=content.metadata,
        preview_images=content.preview_images,
        extract_password=extract_password,
        magnets=magnets,
        ed2k_links=ed2k_links,
        share115_links=share115_links,
        assets=assets,
        primary_link_kind=primary_kind,
        layout=layout,
        quota_link_count=quota_n,
        http_media_count=http_n,
        attachment_names=att_names,
    )
