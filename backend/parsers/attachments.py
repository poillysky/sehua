"""Discuz 附件提取 / 过滤 / 合并（txt · zip · rar · torrent · excel · doc）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from parsers.content import decode_cf_email

ATTACHMENT_DENIED_MARKERS = (
    "只有特定用户可以下载",
    "请先登录",
    "没有权限",
    "无权下载",
    "积分不足",
)

DIRECTORY_ATTACHMENT_MARKERS = (
    "目录",
    "directory",
    "index",
    "树状",
    "文件夹",
    "folder",
    "contents",
)

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
_EXCEL_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".xlsb")
_DOC_SUFFIXES = (".doc", ".docx")


@dataclass(slots=True)
class DownloadAttachment:
    name: str
    url: str
    kind: str  # txt | zip | rar | torrent | excel | doc


@dataclass(slots=True)
class AttachmentFetchResult:
    text: str = ""
    denied: bool = False
    failed: bool = False
    downloaded: bool = False


def is_attachment_denied(html: str) -> bool:
    return any(marker in (html or "") for marker in ATTACHMENT_DENIED_MARKERS)


def _attachment_kind(name: str) -> str | None:
    lower = (name or "").lower().strip()
    if not lower:
        return None
    # 预览图 / 115 截图：文件名常带「115」但不可当链接附件下
    if lower.endswith(_IMAGE_SUFFIXES):
        return None
    if lower.endswith(".torrent"):
        return "torrent"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".rar"):
        return "rar"
    if lower.endswith(_EXCEL_SUFFIXES) or "excel" in lower or "表格" in name:
        return "excel"
    if lower.endswith(_DOC_SUFFIXES):
        return "doc"
    if (
        lower.endswith(".txt")
        or "ed2k" in lower
        or "链接" in name
        or "link" in lower
        or "115" in lower
    ):
        return "txt"
    return None


def _looks_like_directory_attachment(name: str, *, kind: str = "txt") -> bool:
    """仅对 txt 判断目录树；zip/rar 文件名常带「文件夹」仍是资源包。"""
    if kind != "txt":
        return False
    lower = name.lower()
    if lower.endswith("/") or lower.endswith("\\"):
        return True
    return any(marker in name or marker in lower for marker in DIRECTORY_ATTACHMENT_MARKERS)


def _anchor_attachment_name(a) -> str:
    """附件显示名；含 @ 时 Discuz/CF 常写成 [email protected]，需解 data-cfemail。"""
    find_all = getattr(a, "find_all", None)
    if callable(find_all):
        for el in find_all(True):
            enc = ""
            if hasattr(el, "get"):
                enc = (el.get("data-cfemail") or "").strip()
            if enc:
                decoded = decode_cf_email(enc)
                if decoded:
                    return decoded.strip()
    title = (a.get("title") or "").strip() if hasattr(a, "get") else ""
    if title and _attachment_kind(title):
        return title
    name = a.get_text(" ", strip=True) if hasattr(a, "get_text") else ""
    name = (name or "").replace("\xa0", " ").strip()
    return name


def extract_download_attachments(base_url: str, html: str) -> list[DownloadAttachment]:
    """提取帖子内可下载的 txt / zip / rar / torrent / excel / doc（DOM 顺序）。"""
    found: dict[str, DownloadAttachment] = {}
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "lxml")
        for op in soup.select("ignore_js_op, div.pattl, div.tattl"):
            for a in op.select("a[href]"):
                href = a.get("href") or ""
                if "attachment" not in href.lower():
                    continue
                name = _anchor_attachment_name(a)
                if not name:
                    continue
                kind = _attachment_kind(name)
                if not kind:
                    continue
                full = urljoin(base_url, href)
                if name not in found:
                    found[name] = DownloadAttachment(name=name, url=full, kind=kind)
        if found:
            return list(found.values())
    except Exception:
        pass

    # 正则兜底（无 bs4 / 解析失败）；顺带解 CF 邮箱混淆文件名
    for m in re.finditer(
        r'<a\b[^>]*href="([^"]*attachment[^"]*)"[^>]*>(.*?)</a>',
        html or "",
        re.I | re.S,
    ):
        href, inner = m.group(1), m.group(2)
        cf = re.search(r'data-cfemail=["\']([0-9a-fA-F]+)["\']', inner, re.I)
        if cf:
            name = decode_cf_email(cf.group(1)).strip()
        else:
            name = re.sub(r"<[^>]+>", "", inner).replace("\xa0", " ").strip()
        kind = _attachment_kind(name)
        if not kind or name in found:
            continue
        found[name] = DownloadAttachment(name=name, url=urljoin(base_url, href), kind=kind)
    return list(found.values())


# 单帖附件轮询上限（防异常帖挂几十个无关附件）
MAX_ATTACHMENTS_PER_THREAD = 30


def filter_tail_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
) -> list[DownloadAttachment]:
    """txt / excel / doc / zip / rar：按类型排序后逐个轮询（先文本与表格，再压缩包）。"""
    candidates = [
        item
        for item in attachments
        if item.kind in ("txt", "excel", "doc", "zip", "rar")
    ]
    filtered = [
        item
        for item in candidates
        if not _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    if not filtered:
        filtered = [item for item in candidates if item.kind == "txt"]
    order = {"txt": 0, "excel": 1, "doc": 2, "zip": 3, "rar": 4}
    filtered.sort(key=lambda a: (order.get(a.kind, 9), a.name))
    lim = max(1, min(int(limit), MAX_ATTACHMENTS_PER_THREAD))
    return filtered[:lim]


def filter_torrent_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
) -> list[DownloadAttachment]:
    filtered = [item for item in attachments if item.kind == "torrent"]
    lim = max(1, min(int(limit), MAX_ATTACHMENTS_PER_THREAD))
    if len(filtered) <= lim:
        return filtered
    return filtered[:lim]


def filter_all_link_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
) -> list[DownloadAttachment]:
    """全部可抽链附件：txt → excel → doc → zip/rar → torrent，逐个轮询。"""
    tail = filter_tail_attachments(attachments, limit=limit)
    torrents = filter_torrent_attachments(attachments, limit=limit)
    seen: set[str] = set()
    out: list[DownloadAttachment] = []
    for item in [*tail, *torrents]:
        key = f"{item.kind}:{item.name}:{item.url}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def pick_ed2k_attachment_kind(base_url: str, html: str) -> str:
    """电驴板附件策略：有 txt/zip/rar/excel/doc 优先；仅有种子则转磁力。"""
    atts = extract_download_attachments(base_url, html)
    if filter_tail_attachments(atts):
        return "txt_tail"
    if filter_torrent_attachments(atts):
        return "torrent"
    return "txt_tail"


def pick_magnet_attachment_kind(base_url: str, html: str) -> str:
    """磁力板：Excel/Word/文本附件里常有 magnet；否则下种子。"""
    atts = extract_download_attachments(base_url, html)
    if any(a.kind in ("excel", "doc") for a in atts):
        return "txt_tail"
    if filter_torrent_attachments(atts):
        return "torrent"
    if filter_tail_attachments(atts):
        return "txt_tail"
    return "torrent"


def merge_thread_content(post_text: str, attachment_text: str) -> str:
    parts = [part.strip() for part in (post_text, attachment_text) if part and part.strip()]
    return "\n\n".join(parts)


def inject_attachment_text(html: str, attachment_text: str) -> str:
    """把附件解析文本挂到 HTML，便于 judge / parse_thread_dual 复用正文逻辑。"""
    text = (attachment_text or "").strip()
    if not text:
        return html or ""
    cleaned = text.replace("<", " ").replace(">", " ")
    blob = f'\n<div id="postmessage_attach0">{cleaned}</div>\n'
    return (html or "") + blob
