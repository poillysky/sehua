"""Discuz 附件提取 / 过滤 / 合并（txt · zip · rar · torrent）。"""

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


@dataclass(slots=True)
class DownloadAttachment:
    name: str
    url: str
    kind: str  # txt | zip | rar | torrent


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
    """提取帖子内可下载的 txt / zip / rar / torrent（DOM 顺序）。"""
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


def filter_tail_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = 3,
) -> list[DownloadAttachment]:
    """尾部 txt/zip/rar；优先非目录树，跳过纯目录树类。"""
    candidates = [item for item in attachments if item.kind in ("txt", "zip", "rar")]
    filtered = [
        item
        for item in candidates
        if not _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    # 没有链接类附件时，才退回目录树 txt（少数帖只有目录）
    if not filtered:
        filtered = [item for item in candidates if item.kind == "txt"]
    if len(filtered) <= limit:
        return filtered
    # 资源链附件多在前（如 98T@xxx.txt）；目录树/截图已剔除
    return filtered[:limit]


def filter_torrent_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = 3,
) -> list[DownloadAttachment]:
    filtered = [item for item in attachments if item.kind == "torrent"]
    if len(filtered) <= limit:
        return filtered
    return filtered[-limit:]


def pick_ed2k_attachment_kind(base_url: str, html: str) -> str:
    """电驴板附件策略：有 txt/zip/rar 优先；仅有种子则转磁力（板策略本就接受磁力）。"""
    atts = extract_download_attachments(base_url, html)
    if filter_tail_attachments(atts):
        return "txt_tail"
    if filter_torrent_attachments(atts):
        return "torrent"
    return "txt_tail"


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
