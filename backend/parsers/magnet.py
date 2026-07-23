"""Magnet link parsing (infohash / dn / xl)."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass
from urllib.parse import unquote

from parsers.resource_names import SUBRESOURCE_TITLE_MATCH_FORMS

MAGNET_URI_RE = re.compile(r"magnet:\?[^\s<>\"'\]]+", re.I)
BTIH_RE = re.compile(r"xt=urn:btih:([^&]+)", re.I)
DN_RE = re.compile(r"(?:^|&)dn=([^&]+)", re.I)
XL_RE = re.compile(r"(?:^|&)xl=(\d+)", re.I)

# 真子标题取值（简繁；顺序与 SUBRESOURCE_TITLE_MATCH_FORMS 一致）
_SUBRESOURCE_NAME_RES = tuple(
    re.compile(
        rf"【\s*{re.escape(lab)}\s*】\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*$)",
        re.I | re.S,
    )
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS
)
# 【种子名称】/【種子名稱】仅作占位名兜底，不是子标题
_TORRENT_NAME_RE = re.compile(
    r"【\s*(?:种子名称|種子名稱)\s*】\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*$)",
    re.I | re.S,
)
_FILM_SIZE_RE = re.compile(
    r"【\s*影片大小\s*】\s*[:：]?\s*([0-9.]+)\s*(T|TB|G|GB|M|MB|K|KB)?",
    re.I,
)

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


def _clean_label_value(raw: str) -> str:
    text = html_lib.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _size_from_label(raw_num: str, unit: str | None) -> int:
    try:
        val = float(raw_num)
    except (TypeError, ValueError):
        return 0
    u = (unit or "M").upper()
    mult = 1
    if u in {"K", "KB"}:
        mult = 1024
    elif u in {"M", "MB"}:
        mult = 1024**2
    elif u in {"G", "GB"}:
        mult = 1024**3
    elif u in {"T", "TB"}:
        mult = 1024**4
    return int(val * mult)


def _pick_subresource_title(window: str, *, prefer_last: bool) -> str:
    """从窗口取真正子标题值；标签优先级见 SUBRESOURCE_TITLE_LABELS。"""
    if not window:
        return ""
    for cre in _SUBRESOURCE_NAME_RES:
        hits = list(cre.finditer(window))
        if not hits:
            continue
        m = hits[-1] if prefer_last else hits[0]
        name = _clean_label_value(m.group(1))
        if name:
            return name
    return ""


def _context_name_and_size(blob: str, start: int, end: int) -> tuple[str, int]:
    """子资源名只认 SUBRESOURCE_TITLE_LABELS；【种子名称】不是子标题。"""
    before = blob[max(0, start - 280) : start]
    after = blob[end : end + 480]
    before = re.sub(r"<[^>]+>", " ", before)
    after = re.sub(r"<[^>]+>", " ", after)

    # 合集常见：magnet → 【影片名称】/【资源名称】；先看后文，再看前文最近一条
    name = _pick_subresource_title(after, prefer_last=False)
    if not name:
        name = _pick_subresource_title(before, prefer_last=True)
    # 【种子名称】仅作占位名最后兜底
    if not name:
        torr = None
        for m in _TORRENT_NAME_RE.finditer(before):
            torr = m
        if torr:
            name = _clean_label_value(torr.group(1))

    size = 0
    sm = _FILM_SIZE_RE.search(after)
    if sm:
        size = _size_from_label(sm.group(1), sm.group(2))
    return name, size


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
        ctx_name, ctx_size = _context_name_and_size(blob, match.start(), match.end())
        # 上下文名优先于占位 magnet-XXXX；dn= 真实名仍保留优先
        if ctx_name and (parsed.filename.startswith("magnet-") or not parsed.filename):
            parsed = MagnetLink(
                infohash=parsed.infohash,
                filename=ctx_name[:255],
                size=parsed.size or ctx_size,
                link=parsed.link,
            )
        elif ctx_size and not parsed.size:
            parsed = MagnetLink(
                infohash=parsed.infohash,
                filename=parsed.filename,
                size=ctx_size,
                link=parsed.link,
            )
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
