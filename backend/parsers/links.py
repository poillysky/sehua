"""Dual magnet + ed2k link extraction facade."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from parsers.content import (
    ThreadContent,
    build_structured_description,
    parse_thread_content,
)
from parsers.ed2k import Ed2kLink, parse_ed2k_text, pick_primary_ed2k
from parsers.magnet import MagnetLink, parse_magnet_text, pick_primary_magnet

LinkKind = Literal["magnet", "ed2k", "both", "none"]


@dataclass(slots=True)
class ParsedAsset:
    link_kind: Literal["magnet", "ed2k"]
    hash: str
    filename: str
    size: int
    uri: str
    is_primary: bool = False


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
    assets: list[ParsedAsset] = field(default_factory=list)
    primary_link_kind: Literal["magnet", "ed2k", "none"] = "none"

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
) -> tuple[list[ParsedAsset], Literal["magnet", "ed2k", "none"]]:
    """Merge both link types; choose one primary according to board preference."""
    assets: list[ParsedAsset] = []

    primary_magnet = pick_primary_magnet(magnets) if magnets else None
    primary_ed2k = pick_primary_ed2k(ed2k_links) if ed2k_links else None

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
                filename=link.filename,
                size=link.size,
                uri=link.link,
                is_primary=False,
            )
        )

    primary_kind: Literal["magnet", "ed2k", "none"] = "none"
    if preferred == "magnet":
        primary_kind = "magnet" if primary_magnet else ("ed2k" if primary_ed2k else "none")
    elif preferred == "ed2k":
        primary_kind = "ed2k" if primary_ed2k else ("magnet" if primary_magnet else "none")
    else:
        # both / none: prefer magnet when both exist
        if primary_magnet:
            primary_kind = "magnet"
        elif primary_ed2k:
            primary_kind = "ed2k"

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
    Full dual parse: HTML → structured content + magnet + ed2k assets.

    preferred_link: board policy — 'magnet' | 'ed2k' | 'both'
    extra_text: 附件解析出的文本（txt/zip/rar 内链或 torrent→magnet）并入语料
    board_fid: 用于按板块结构卡片筛选描述字段
    """
    content = parse_thread_content(html, tid=tid, base_url=base_url)
    corpus = "\n".join(
        part
        for part in (
            content.blockcode_text,
            content.plain_text,
            content.title,
            extra_text or "",
        )
        if part
    )
    magnets, ed2k_links = parse_links_from_text(corpus)
    assets, primary_kind = build_assets(magnets, ed2k_links, preferred=preferred_link)
    description = _build_description(content, board_fid=board_fid)

    return DualParseResult(
        tid=content.tid or tid,
        title=content.title,
        description=description,
        metadata=content.metadata,
        preview_images=content.preview_images,
        extract_password=content.extract_password,
        magnets=magnets,
        ed2k_links=ed2k_links,
        assets=assets,
        primary_link_kind=primary_kind,
    )
