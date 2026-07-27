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

# 2048 附件 txt 常见：缺 | 把 扩展名+大小+hash 粘在一起
# ed2k://|file|www.98T.la@AMBI-039.mp4206253751428B6B3…421
_GLUED_ED2K_RE = re.compile(
    r"ed2k://\|file\|"
    r"([^\|\r\n]+?\."
    r"(?:mp4|mkv|avi|wmv|ts|iso|mov|flv|m4v|rmvb|mpg|mpeg|zip|rar|7z|txt))"
    r"(\d{3,})"
    r"([0-9A-Fa-f]{32})"
    r"(?:\|/?|/)?",
    re.IGNORECASE,
)

_FULLWIDTH_TRANS = str.maketrans(
    {
        "：": ":",
        # 注意：勿把「｜」全局换成「|」——中文片名常含全角竖线（如「精华版｜梦幻」），
        # 换掉后会把 filename 拆成多余字段，导致整链匹配失败。
        "／": "/",
        "．": ".",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
        "\u00ad": "",
    }
)

# 仅还原「结构全角竖线」的电驴链：ed2k://｜file｜名｜大小｜hash｜
_FW_STRUCT_ED2K_RE = re.compile(
    r"ed2k://\s*｜\s*file\s*｜([^｜]+?)｜(\d+)｜([A-Fa-f0-9]{32})｜",
    re.IGNORECASE,
)

_ENTITY_PIPE_RE = re.compile(r"&vert;|&#0*124;|&#x0*7c;", re.I)

ARCHIVE_EXTENSIONS = (".zip", ".rar", ".7z", ".cbz", ".cbr")

# 单文件合理上限；超过视为 xl/解析炸档（例：tid=1556002 入库 9 万 GB）
MAX_REASONABLE_FILE_BYTES = 32 * (1024**4)

_ED2K_SIZE_IN_URI_RE = re.compile(
    r"ed2k://\|file\|[^|\n]{1,400}\|(\d+)\|[A-Fa-f0-9]{32}\|",
    re.I,
)


def size_from_ed2k_uri(uri: str | None) -> int:
    """从 ed2k URI 抽取 size 字段；超上限视为不可信。"""
    m = _ED2K_SIZE_IN_URI_RE.search(uri or "")
    if not m:
        return 0
    n = int(m.group(1))
    return n if 0 < n <= MAX_REASONABLE_FILE_BYTES else 0


def coerce_file_size(size: int, uris: list[str] | None = None) -> int:
    """纠正炸档 / 空 size：优先可信链内尺寸。"""
    n = int(size or 0)
    uri_sizes = [size_from_ed2k_uri(u) for u in (uris or [])]
    uri_sizes = [s for s in uri_sizes if s > 0]
    best_uri = max(uri_sizes) if uri_sizes else 0
    if n <= 0:
        return best_uri
    if n > MAX_REASONABLE_FILE_BYTES:
        return best_uri
    # 入库 size 远大于链内 xl（误把其它字段当字节）
    if best_uri and n > best_uri * 8 and n > best_uri + 2 * (1024**3):
        return best_uri
    return n


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
    # 结构全角竖线 → ASCII（保留文件名里的全角｜）
    out = _FW_STRUCT_ED2K_RE.sub(
        lambda m: f"ed2k://|file|{m.group(1).strip()}|{m.group(2)}|{m.group(3).upper()}|/",
        out,
    )
    out = _TRUNCATED_ED2K_SCHEME_RE.sub("ed2k://|file|", out)
    out = _SPACED_ED2K_SCHEME_RE.sub("ed2k://|file|", out)
    out = _ED2K_SLASH_FIX_RE.sub("ed2k://|file|", out)
    out = _ED2K_SPACED_PIPES_RE.sub(
        lambda m: f"ed2k://|file|{m.group(1).strip()}|{m.group(2)}|{m.group(3).upper()}|/",
        out,
    )
    out = _GLUED_ED2K_RE.sub(
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
        if size > MAX_REASONABLE_FILE_BYTES:
            size = 0
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
