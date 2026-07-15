"""Discuz 附件提取 / 过滤 / 合并（txt · zip · rar · torrent）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

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
    lower = name.lower()
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


def _looks_like_directory_attachment(name: str) -> bool:
    lower = name.lower()
    if lower.endswith("/") or lower.endswith("\\"):
        return True
    return any(marker in name or marker in lower for marker in DIRECTORY_ATTACHMENT_MARKERS)


def extract_download_attachments(base_url: str, html: str) -> list[DownloadAttachment]:
    """提取帖子内可下载的 txt / zip / rar / torrent（DOM 顺序）。"""
    found: dict[str, DownloadAttachment] = {}
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "lxml")
        for op in soup.select("ignore_js_op, div.pattl, div.tattl"):
            for a in op.select("a[href]"):
                href = a.get("href") or ""
                name = a.get_text(strip=True)
                if not name or "attachment" not in href.lower():
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

    # 正则兜底（无 bs4 / 解析失败）
    for m in re.finditer(
        r'href="([^"]*attachment[^"]*)"[^>]*>([^<]+)</a>',
        html or "",
        re.I,
    ):
        href, name = m.group(1), m.group(2).strip()
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
    """尾部 txt/zip/rar，跳过目录树类。"""
    filtered = [
        item
        for item in attachments
        if item.kind in ("txt", "zip", "rar") and not _looks_like_directory_attachment(item.name)
    ]
    if len(filtered) <= limit:
        return filtered
    return filtered[-limit:]


def filter_torrent_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = 3,
) -> list[DownloadAttachment]:
    filtered = [item for item in attachments if item.kind == "torrent"]
    if len(filtered) <= limit:
        return filtered
    return filtered[-limit:]


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
