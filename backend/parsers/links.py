"""Dual magnet + ed2k (+ 115 分享码) link extraction facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from parsers.content import (
    ThreadContent,
    build_structured_description,
    extract_blockcode_text,
    extract_link_corpus_html,
    extract_password as extract_post_password,
    extract_subresource_blocks,
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
    Full dual parse: HTML → structured content + magnet + ed2k (+ 115 分享) assets.

    preferred_link: board policy — 'magnet' | 'ed2k' | 'both'
    extra_text: 附件解析出的文本（txt/zip/rar 内链或 torrent→magnet）并入语料
    board_fid: 用于按板块结构卡片筛选描述字段

    元数据仍取主贴字段；链接/子资源认楼主各层（含二楼补链），路人回帖不参与。
    """
    content = parse_thread_content(html, tid=tid, base_url=base_url)
    link_html = extract_link_corpus_html(html)
    link_block = extract_blockcode_text(link_html) if link_html else ""
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
    # 子资源：按子标题切段（无子标题则整帖用帖标题）；一段只留一个主链
    hashes = [a.hash for a in assets if a.link_kind in {"magnet", "ed2k"} and a.hash]
    if hashes:
        blocks = extract_subresource_blocks(
            html,
            hashes,
            base_url=base_url,
            limit_per=5,
            fallback_title=content.title or "",
        )
        if blocks:
            by_hash = {(a.hash or "").strip().upper(): a for a in assets}
            ordered: list[ParsedAsset] = []
            for b in blocks:
                asset = by_hash.get(b.infohash)
                if not asset:
                    continue
                if b.title:
                    asset.filename = b.title[:255]
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
                assets = ordered
                primary_kind = ordered[0].link_kind  # type: ignore[assignment]
    description = _build_description(content, board_fid=board_fid)

    extract_password = content.extract_password
    if not extract_password and link_html:
        extract_password = extract_post_password(link_html) or ""
    if primary_kind == "115share":
        primary = next((a for a in assets if a.is_primary), None)
        if primary and primary.access_code:
            extract_password = primary.access_code

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
    )
