"""Magnet link parsing (infohash / dn / xl)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

MAGNET_URI_RE = re.compile(r"magnet:\?[^\s<>\"'\]]+", re.I)
BTIH_RE = re.compile(r"xt=urn:btih:([^&]+)", re.I)
DN_RE = re.compile(r"(?:^|&)dn=([^&]+)", re.I)
XL_RE = re.compile(r"(?:^|&)xl=(\d+)", re.I)

# 中文编辑粘贴常见：全角冒号/问号/与号/等号
_FULLWIDTH_TRANS = str.maketrans(
    {
        "：": ":",
        "？": "?",
        "＆": "&",
        "＝": "=",
    }
)

# magnet : ? xt = urn : btih : HASH（半角被空格打断）
_SPACED_MAGNET_CORE_RE = re.compile(
    r"magnet\s*:\s*\?\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    r"([A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})",
    re.I,
)

# 发帖/附件防和谐：去掉冒号 → magnetxt=urnbtih:HASH 或 magnet?xt=urnbtih:HASH
_COLONLESS_MAGNET_RE = re.compile(
    r"magnet\s*\??\s*xt\s*=\s*urn\s*btih\s*:\s*"
    r"([A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})",
    re.I,
)


def normalize_magnet_corpus(text: str) -> str:
    """把全角标点 / 被空格拆开 / 去冒号防和谐的磁力还原成标准形式。"""
    if not text:
        return ""
    out = text.translate(_FULLWIDTH_TRANS)
    out = _SPACED_MAGNET_CORE_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _COLONLESS_MAGNET_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    return out


@dataclass(slots=True)
class MagnetLink:
    infohash: str
    filename: str
    size: int
    link: str


def _normalize_infohash(raw: str) -> str:
    return unquote(raw.strip()).upper()


def _parse_magnet_uri(uri: str) -> MagnetLink | None:
    match = BTIH_RE.search(uri)
    if not match:
        return None

    infohash = _normalize_infohash(match.group(1))
    if not infohash:
        return None

    query = uri.split("?", 1)[-1]
    filename = ""
    dn_match = DN_RE.search(query)
    if dn_match:
        filename = unquote(dn_match.group(1).replace("+", " ")).strip()

    size = 0
    xl_match = XL_RE.search(query)
    if xl_match:
        size = int(xl_match.group(1))

    if not filename:
        filename = f"magnet-{infohash[:8]}"

    return MagnetLink(infohash=infohash, filename=filename, size=size, link=uri)


def parse_magnet_text(text: str) -> list[MagnetLink]:
    results: list[MagnetLink] = []
    seen: set[str] = set()
    blob = normalize_magnet_corpus(text or "")

    for match in MAGNET_URI_RE.finditer(blob):
        parsed = _parse_magnet_uri(match.group(0))
        if not parsed or parsed.infohash in seen:
            continue
        seen.add(parsed.infohash)
        results.append(parsed)

    return results


def pick_primary_magnet(links: list[MagnetLink]) -> MagnetLink | None:
    if not links:
        return None
    sized = [link for link in links if link.size > 0]
    if sized:
        return max(sized, key=lambda item: item.size)
    return links[0]
