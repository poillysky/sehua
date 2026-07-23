"""Magnet link parsing (infohash / dn / xl)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from parsers.resource_names import context_subresource_title

MAGNET_URI_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?:[A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})(?:&[^\s<>\"'\]【】]+)?",
    re.I,
)
BTIH_RE = re.compile(
    r"xt=urn:btih:([A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})",
    re.I,
)

DN_RE = re.compile(r"(?:^|&)dn=([^&]+)", re.I)
XL_RE = re.compile(r"(?:^|&)xl=(\d+)", re.I)

_FILM_SIZE_RE = re.compile(
    r"【\s*(?:影片大小|影片容量|资源大小|資源大小|文件大小|檔案大小|档案大小)\s*】"
    r"\s*[:：]?\s*([0-9.]+)\s*(T|TB|G|GB|M|MB|K|KB)?",
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

# Discuz「复制代码」旁裸 infohash（例：复制代码下载：f7809dc8…）
# 转帖常见【哈希校验】：40位 hex（tid 3628517）
#
# 禁止用裸「磁力」「BT」作线索：标题【BT/磁力】在大 HTML 上会触发灾难性回溯卡死进程。
# 间隔必须有上限，禁止 (?:…)*? 扫整页。
_BARE_INFOHASH_CUED_RE = re.compile(
    r"(?:"
    r"复制代码(?:下载)?"
    r"|哈希校验"
    r"|哈希值"
    r"|磁力(?:链接|连接|鍊接)"
    r"|BT\s*(?:哈希|hash)"
    r"|info\s*hash"
    r"|种子(?:哈希|hash)"
    r")"
    r"(?:[\s:：\|\[\]【】=\-_]|<[^>\n]{0,120}>){0,60}"
    r"([A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})"
    r"(?![A-Fa-f0-9])",
    re.I,
)


def _already_magnet_btih(text: str, hash_value: str) -> bool:
    return bool(
        re.search(
            rf"(?:magnet:\?|btih:)[^\n]{{0,40}}{re.escape(hash_value)}",
            text,
            re.I,
        )
    )


def _expand_bare_infohashes(text: str) -> str:
    """把带提示语的裸 infohash 原地换成 magnet:?xt=urn:btih:…，便于后续统一解析。"""
    if not text:
        return ""

    def repl(m: re.Match[str]) -> str:
        h = m.group(1)
        before = text[max(0, m.start(1) - 32) : m.start(1)].lower()
        if "btih:" in before or "magnet:?" in before:
            return m.group(0)
        if _already_magnet_btih(text, h):
            return m.group(0)
        head = m.group(0)[: m.start(1) - m.start()]
        tail = m.group(0)[m.end(1) - m.start() :]
        # 与后文【标签】隔开，避免 magnet URI 吞进中文
        return f"{head}magnet:?xt=urn:btih:{h} {tail}"

    return _BARE_INFOHASH_CUED_RE.sub(repl, text)


def normalize_magnet_corpus(text: str) -> str:
    """把全角标点 / 被空格拆开 / 去冒号防和谐 / 裸 infohash 还原成标准形式。"""
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
    out = _expand_bare_infohashes(out)
    return out


@dataclass(slots=True)
class MagnetLink:
    infohash: str
    filename: str
    size: int
    link: str


def _normalize_infohash(raw: str) -> str:
    return unquote(raw.strip()).upper()


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


def _context_name_and_size(blob: str, start: int, end: int) -> tuple[str, int]:
    """子资源名只认【影片名称】/【资源名称】；尺寸与片名同侧就近取。"""
    name = context_subresource_title(
        blob, start, end, allow_torrent_fallback=True
    )
    before = re.sub(r"<[^>]+>", " ", blob[max(0, start - 800) : start])
    after = re.sub(r"<[^>]+>", " ", blob[end : end + 480])
    size = 0
    # 与命名一致：先后文再前文，避免吃到上一条的【影片大小】
    for window in (after, before):
        sm = _FILM_SIZE_RE.search(window)
        if sm:
            size = _size_from_label(sm.group(1), sm.group(2))
            break
    if not size and name:
        emb = re.search(
            r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
            name,
            re.I,
        )
        if emb:
            size = _size_from_label(emb.group(1), emb.group(2))
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
        # 子资源名 = 帖内【影片名称】/【资源名称】，优先于 dn= 链内名
        if ctx_name:
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
