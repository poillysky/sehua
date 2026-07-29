"""ED2K link parsing."""

from __future__ import annotations

import html
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

# Discuz BBCode：含 @ 文件名常被包成 [url]…[/url]（CF 解出后仍残留，会被 hard_dirty 整链丢掉）
_BBCODE_URL_WRAP_RE = re.compile(r"\[url(?:=[^\]]*)?\](.*?)\[/url\]", re.I | re.S)
# Discuz 用户卡片：www.98T.la[url=home.php?mod=space&uid=N]@[/url] (1).mp4
# → 内层仅一个 @，须先还原，否则 salvage 会误捞成 (1).mp4（tid=3304545）
_DISCUZ_AT_MENTION_URL_RE = re.compile(r"\[url=[^\]]+\]@\[/url\]", re.I)

# Discuz 把含 @ 的 ed2k 渲成嵌套 <a>/script 时：|file| 段脏，但尾巴 |size|hash|/ 常还在
# （tid=3405418：href 被拆、插 (0 Bytes)/script，后缀仍有 |976158193|B9DF…|/）
_ED2K_HTML_POISONED_RE = re.compile(
    r"ed2k://\|file\|"
    r"(.{0,3000}?)"
    r"\|(\d{3,})\|([A-Fa-f0-9]{32})\|/?",
    re.IGNORECASE | re.DOTALL,
)
_ED2K_NAME_EXT = (
    r"mp4|mkv|avi|wmv|ts|iso|mov|flv|m4v|rmvb|mpg|mpeg|zip|rar|7z|txt|ssa|ass"
)
_ED2K_HREF_NAME_RE = re.compile(
    rf"""href=["'](?:https?://)?(www\.[^"'<>\s]+@[^"'<>\s]+\.(?:{_ED2K_NAME_EXT}))["']""",
    re.I,
)
_ED2K_PLAIN_NAME_RE = re.compile(
    rf"(www\.[^\s\[\]<>\"']+@[^\s\[\]<>\"']+\.(?:{_ED2K_NAME_EXT}))",
    re.I,
)
_ED2K_ANY_FILE_RE = re.compile(
    rf"([^\s\[\]<>\"']{{1,180}}\.(?:{_ED2K_NAME_EXT}))",
    re.I,
)
_SCRIPT_BLOCK_RE = re.compile(r"(?is)<script\b[^>]*>.*?</script>")

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


def _extract_ed2k_filename_from_junk(junk: str) -> str:
    """从 Discuz/CF 插烂的 |file| 段里捞真实文件名。"""
    raw = junk or ""
    m = _ED2K_HREF_NAME_RE.search(raw)
    if m:
        return html.unescape(m.group(1)).strip().rstrip("[/")
    cleaned = _SCRIPT_BLOCK_RE.sub(" ", raw)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html.unescape(cleaned)
    # 先还原 @用户卡片，再剥普通 [url]包名
    cleaned = _DISCUZ_AT_MENTION_URL_RE.sub("@", cleaned)
    cleaned = _BBCODE_URL_WRAP_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"\(\s*0\s*Bytes\s*\)", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 整段已是「…扩展名」：允许 www.x@ (1).mp4 这类空格，勿再被 ANY 切成 (1).mp4
    m = re.fullmatch(
        rf"(.+\.(?:{_ED2K_NAME_EXT}))",
        cleaned,
        flags=re.I,
    )
    if m:
        name = m.group(1).strip().rstrip("[/")
        if (
            name
            and "|" not in name
            and "bytes" not in name.lower()
            and not name.lower().startswith("http")
            and not _is_poisoned_ed2k_filename(name)
        ):
            return name
    m = _ED2K_PLAIN_NAME_RE.search(cleaned)
    if m:
        return m.group(1).strip().rstrip("[/")
    m = _ED2K_ANY_FILE_RE.search(cleaned)
    if m:
        name = m.group(1).strip().rstrip("[/")
        # 拒绝明显 UI 残片
        if "bytes" in name.lower() or name.startswith("http"):
            return ""
        return name
    return ""


def _salvage_html_poisoned_ed2k(text: str) -> str:
    """把「|file| + HTML 残骸 + |size|hash|」拼回干净 ed2k URI。"""

    def _repl(match: re.Match[str]) -> str:
        junk, size, file_hash = match.group(1), match.group(2), match.group(3)
        # 已是干净名则不动，交给后续路径
        if (
            "<" not in junk
            and "[url" not in junk.lower()
            and "script" not in junk.lower()
            and "\n" not in junk
            and len(junk) < 300
        ):
            return match.group(0)
        name = _extract_ed2k_filename_from_junk(junk)
        if not name or _is_poisoned_ed2k_filename(name):
            return match.group(0)
        return f"ed2k://|file|{name}|{size}|{file_hash.upper()}|/"

    return _ED2K_HTML_POISONED_RE.sub(_repl, text or "")


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
    # Discuz @用户卡片嵌进文件名：须在 HTML salvage / 剥 [url] 之前还原成裸 @
    out = _DISCUZ_AT_MENTION_URL_RE.sub("@", out)
    # Discuz 嵌套 <a>/script 残骸（须在剥 [url] 前，保留 href 线索）
    out = _salvage_html_poisoned_ed2k(out)
    # [url]www.98T.la@xxx.mp4[/url] → 裸文件名（tid=3219637 等）
    out = _BBCODE_URL_WRAP_RE.sub(r"\1", out)
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


def _is_poisoned_ed2k_filename(filename: str) -> bool:
    """CF 邮件保护 / HTML 残片进了 |file| 段 → 整链丢弃（同 hash 常另有干净副本）。"""
    from parsers.resource_names import is_hard_dirty_filename

    name = (filename or "").strip()
    if not name:
        return True
    # 残缺 CF 解码常出单字母/极短垃圾（如 data-cfemail 过短 → "w"）
    if len(name) < 3:
        return True
    if is_hard_dirty_filename(name):
        return True
    low = name.lower()
    if "cdn-cgi" in low or "email-protection" in low or "__cf_email__" in low:
        return True
    if "<" in name or ">" in name:
        return True
    return False


def parse_ed2k_text(text: str) -> list[Ed2kLink]:
    from parsers.content import restore_cloudflare_emails
    from parsers.resource_names import context_subresource_title

    results: list[Ed2kLink] = []
    # 按完整 URI 去重：同 hash 但文件名不同仍保留（配额按「下载份」计，
    # 如 tid=3524065 末条与首条同 hash、不同名，勿并成漏链）
    seen: set[str] = set()
    # 先解 CF 邮件保护，再 normalize（含剥 [url]），否则 |file| 段带 HTML/[url] 会被整链丢弃
    blob = normalize_ed2k_corpus(restore_cloudflare_emails(text or ""))

    for match in ED2K_RE.finditer(blob):
        # 帖内常同时出现 & 与 &amp; 两份同链；解实体后再去重
        filename = html.unescape(match.group(1).strip())
        if _is_poisoned_ed2k_filename(filename):
            continue
        size = int(match.group(2))
        if size > MAX_REASONABLE_FILE_BYTES:
            size = 0
        file_hash = match.group(3).upper()
        link = build_ed2k_link(filename, size, file_hash)
        if link in seen:
            continue
        seen.add(link)
        display = context_subresource_title(blob, match.start(), match.end())
        results.append(
            Ed2kLink(
                filename=filename,
                size=size,
                hash=file_hash,
                link=link,
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
