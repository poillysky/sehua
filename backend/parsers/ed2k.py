"""ED2K link parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

ED2K_RE = re.compile(
    r"ed2k://\|file\|([^\|]+)\|(\d+)\|([A-Fa-f0-9]{32})\|",
    re.IGNORECASE,
)

# 发帖人/站点常把协议掐掉字母：d2k / e2k / edk / ed2 → ed2k
_TRUNCATED_ED2K_SCHEME_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:d2k|e2k|edk|ed2)\s*:\s*(?:/\s*){0,3}\|?\s*file\s*\|",
    re.IGNORECASE,
)

# e d 2 k : / / | file |（字母间至少一处空格，避免误伤正常 ed2k）
_SPACED_ED2K_SCHEME_RE = re.compile(
    r"(?<![A-Za-z0-9])e\s+d\s+2\s+k\s*:\s*(?:/\s*){0,3}\|?\s*file\s*\|",
    re.IGNORECASE,
)

# 缺斜杠 / 多斜杠：ed2k:|file| / ed2k:/|file| / ed2k:///|file|
_ED2K_SLASH_FIX_RE = re.compile(
    r"(?<![A-Za-z0-9])ed2k\s*:\s*(?:/\s*){0,3}\|?\s*file\s*\|",
    re.IGNORECASE,
)

# 管道旁空格：ed2k:// | file | name | size | hash |
_ED2K_SPACED_PIPES_RE = re.compile(
    r"ed2k://\s*\|\s*file\s*\|\s*([^\|]+?)\s*\|\s*(\d+)\s*\|\s*([A-Fa-f0-9]{32})\s*\|",
    re.IGNORECASE,
)

_FULLWIDTH_TRANS = str.maketrans(
    {
        "：": ":",
        "｜": "|",
        "／": "/",
        "．": ".",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
        "\u00ad": "",
    }
)

_ENTITY_PIPE_RE = re.compile(r"&vert;|&#0*124;|&#x0*7c;", re.I)

ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z", ".cbz", ".cbr")


@dataclass(slots=True)
class Ed2kLink:
    filename: str
    size: int
    hash: str
    link: str
    # 帖内【影片名称】/【资源名称】；空则入库时用主标题，不用链内 filename
    display_name: str = ""


def normalize_ed2k_corpus(text: str) -> str:
    """还原被掐字母 / 全角 / 空格拆开 / 缺斜杠的 ed2k 协议头。"""
    if not text:
        return ""
    out = text.translate(_FULLWIDTH_TRANS)
    out = _ENTITY_PIPE_RE.sub("|", out)
    out = _TRUNCATED_ED2K_SCHEME_RE.sub("ed2k://|file|", out)
    out = _SPACED_ED2K_SCHEME_RE.sub("ed2k://|file|", out)
    out = _ED2K_SLASH_FIX_RE.sub("ed2k://|file|", out)
    out = _ED2K_SPACED_PIPES_RE.sub(
        lambda m: f"ed2k://|file|{m.group(1).strip()}|{m.group(2)}|{m.group(3).upper()}|/",
        out,
    )
    return out


def build_ed2k_link(filename: str, size: int, file_hash: str) -> str:
    return f"ed2k://|file|{filename}|{size}|{file_hash.upper()}|/"


def build_search_string(
    filename: str,
    title: str = "",
    description: str = "",
    extract_password: str = "",
) -> str:
    parts: list[str] = []
    for item in (filename, title, description, extract_password):
        text = (item or "").strip()
        if text and text not in parts:
            parts.append(text)
    return " ".join(parts)


def parse_ed2k_text(text: str) -> list[Ed2kLink]:
    from parsers.resource_names import context_subresource_title

    results: list[Ed2kLink] = []
    seen: set[str] = set()
    blob = normalize_ed2k_corpus(text or "")

    for match in ED2K_RE.finditer(blob):
        filename = match.group(1).strip()
        size = int(match.group(2))
        file_hash = match.group(3).upper()
        if file_hash in seen:
            continue
        seen.add(file_hash)
        display = context_subresource_title(blob, match.start(), match.end())
        results.append(
            Ed2kLink(
                filename=filename,
                size=size,
                hash=file_hash,
                link=build_ed2k_link(filename, size, file_hash),
                display_name=(display[:255] if display else ""),
            )
        )

    return results


def pick_primary_ed2k(links: list[Ed2kLink]) -> Ed2kLink | None:
    """Prefer archives; otherwise largest size."""
    if not links:
        return None
    archives = [link for link in links if link.filename.lower().endswith(ARCHIVE_EXTENSIONS)]
    if archives:
        return max(archives, key=lambda item: item.size)
    return max(links, key=lambda item: item.size)
