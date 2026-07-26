"""Discuz 附件提取 / 过滤 / 合并（txt · zip · rar · torrent · excel · doc）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from parsers.content import decode_cf_email

# 附件下载响应页 / 楼主区「真·附件无权」提示。
# 勿用过宽词：全站脚本常有「请先登录再打赏」→ 会把无附件的磁链帖误标无权。
ATTACHMENT_DENIED_MARKERS = (
    "只有特定用户可以下载",
    "请先登录后下载",
    "请先登录才能下载",
    "请先登录后才能下载",
    "没有权限下载",
    "无权下载",
    "积分不足",
    "您所在的用户组无法下载或查看附件",
    "用户组无法下载或查看附件",
    "无法下载或查看附件",
)

# 附件直链落到 PHPWind「提示信息」：日限 / 次数用尽（与无权同占位）。
ATTACHMENT_LIMIT_MARKERS = (
    "今天下载",
    "请明天再来",
    "今日下载次数",
    "下载次数已达",
    "下载次数已用完",
    "附件下载次数",
)

# 附件直链落到 PHPWind「提示信息」登录页（未登录），不是用户组无权。
ATTACHMENT_LOGIN_MARKERS = (
    "您没有登录或者没有权限访问此页面",
    "您没有登录或没有权限访问此页面",
)

# 楼主正文里出现这些才算「帖内附件无权」（不含全页导航）
THREAD_BODY_ATTACH_DENIED_MARKERS = (
    "您所在的用户组无法下载或查看附件",
    "用户组无法下载或查看附件",
    "无法下载或查看附件",
    "只有特定用户可以下载",
    "无权下载此附件",
    "无权下载该附件",
    "没有权限下载附件",
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
    login_required: bool = False
    failed: bool = False
    downloaded: bool = False


def is_attachment_login_required(html: str) -> bool:
    """附件下载是否落到 PHPWind 未登录提示页。"""
    text = html or ""
    if not text:
        return False
    return any(marker in text for marker in ATTACHMENT_LOGIN_MARKERS)


def is_attachment_download_limited(html: str) -> bool:
    """附件下载是否落到日限/次数上限提示页。"""
    text = html or ""
    if not text:
        return False
    return any(marker in text for marker in ATTACHMENT_LIMIT_MARKERS)


def is_attachment_denied(html: str) -> bool:
    """附件下载响应或帖内是否出现无权/需登录/日限提示。

    会剔除「请先登录再打赏」等非附件文案，避免 2048 全页脚本误伤。
    未登录 / 日限提示页也算 denied → 占位「无权限下载附件」（勿跳过）。
    """
    text = html or ""
    if not text:
        return False
    if is_attachment_login_required(text):
        return True
    if is_attachment_download_limited(text):
        return True
    # 打赏 / 导航：alert('请先登录再打赏') —— 不是附件无权
    cleaned = text.replace("请先登录再打赏", "")
    return any(marker in cleaned for marker in ATTACHMENT_DENIED_MARKERS)


def thread_body_shows_attach_denied(html: str) -> bool:
    """仅楼主区明示附件无权（有种子/txt 可下时不要只靠全页扫描）。"""
    scope = ""
    try:
        from parsers.content import extract_lz_scope_html

        scope = extract_lz_scope_html(html) or ""
    except Exception:
        scope = ""
    blob = scope or ""
    if not blob:
        return False
    return any(marker in blob for marker in THREAD_BODY_ATTACH_DENIED_MARKERS)


def _is_attachment_href(href: str) -> bool:
    """Discuz attachment=… / PHPWind job.php?action=download&aid=…"""
    h = (href or "").lower()
    if not h:
        return False
    if "attachment" in h:
        return True
    if "action=download" in h or "job=download" in h:
        return True
    if "aid=" in h and ("job.php" in h or "download" in h):
        return True
    return False


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
    """提取帖子内可下载的 txt / zip / rar / torrent / excel / doc（DOM 顺序）。

    兼容 Discuz（forum.php?mod=attachment）与 PHPWind（job.php?action=download）。
    """
    found: dict[str, DownloadAttachment] = {}
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "lxml")
        # Discuz 附件区 + PHPWind attach-card
        nodes = soup.select(
            "ignore_js_op, div.pattl, div.tattl, div.attach-card, "
            "a.attach-name-link, a[href*='attachment'], a[href*='action=download']"
        )
        for node in nodes:
            anchors = (
                [node]
                if getattr(node, "name", None) == "a" and node.get("href")
                else node.select("a[href]")
            )
            for a in anchors:
                href = a.get("href") or ""
                if not _is_attachment_href(href):
                    continue
                name = _anchor_attachment_name(a)
                if not name:
                    # PHPWind 常把文件名放在邻近 span / img alt
                    parent = a.find_parent("div", class_="attach-card") or a.parent
                    if parent is not None:
                        icon = parent.select_one("img[alt]")
                        alt = (icon.get("alt") or "").strip() if icon else ""
                        span = a.select_one("span") or (
                            parent.select_one(".attach-name-link span")
                        )
                        span_txt = span.get_text(" ", strip=True) if span else ""
                        name = span_txt or (f"file.{alt}" if alt else "")
                if not name:
                    continue
                kind = _attachment_kind(name)
                if not kind:
                    # 文件名无后缀时：用 torrent.gif / alt=torrent 推断
                    parent = a.find_parent("div", class_="attach-card")
                    if parent is not None:
                        icon = parent.select_one("img[src*='torrent'], img[alt='torrent']")
                        if icon is not None and not name.lower().endswith(".torrent"):
                            name = f"{name}.torrent"
                            kind = "torrent"
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
        r'<a\b[^>]*href="([^"]*(?:attachment|action=download|job=download)[^"]*)"[^>]*>(.*?)</a>',
        html or "",
        re.I | re.S,
    ):
        href, inner = m.group(1), m.group(2)
        if not _is_attachment_href(href):
            continue
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

# 内存 / zip bomb 防护：链文件包通常 ≪1MB；超大附件多为误挂视频包
MAX_ATTACHMENT_BYTES = 12 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_DEPTH = 4
# 二进制扫 magnet/ed2k：超大文件只扫头尾，避免整文件三份解码
MAX_BINARY_LINK_SCAN_BYTES = 2 * 1024 * 1024


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


# 按板块主链频次：多附件时先试更可能含目标链的类型
_ATTACH_ORDER_ED2K = {
    "txt": 0,
    "zip": 1,
    "rar": 2,
    "excel": 3,
    "doc": 4,
    "torrent": 5,
}
_ATTACH_ORDER_MAGNET = {
    "torrent": 0,
    "excel": 1,
    "doc": 2,
    "txt": 3,
    "zip": 4,
    "rar": 5,
}


def _attach_kind_order(preferred_link: str | None) -> dict[str, int]:
    pref = (preferred_link or "ed2k").strip().lower()
    if pref in {"magnet", "both"}:
        return _ATTACH_ORDER_MAGNET
    return _ATTACH_ORDER_ED2K


def filter_all_link_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
    preferred_link: str | None = None,
) -> list[DownloadAttachment]:
    """全部可抽链附件，按板块主链类型排序后逐个轮询。

    - 电驴板：txt → zip/rar → excel/doc → torrent
    - 磁力/双链：torrent → excel/doc/txt → zip/rar
    """
    candidates = [
        item
        for item in attachments
        if item.kind in ("txt", "excel", "doc", "zip", "rar", "torrent")
    ]
    filtered = [
        item
        for item in candidates
        if item.kind == "torrent"
        or not _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    # 目录类过滤后若只剩空：保留 txt（与 filter_tail 一致）
    if not filtered:
        filtered = [item for item in candidates if item.kind == "txt"]
    order = _attach_kind_order(preferred_link)
    filtered.sort(key=lambda a: (order.get(a.kind, 9), a.name))
    lim = max(1, min(int(limit), MAX_ATTACHMENTS_PER_THREAD))
    return filtered[:lim]


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
    from parsers.safe_text import strip_nul

    text = strip_nul(attachment_text or "").strip()
    if not text:
        return html or ""
    cleaned = text.replace("<", " ").replace(">", " ")
    blob = f'\n<div id="postmessage_attach0">{cleaned}</div>\n'
    return (html or "") + blob
