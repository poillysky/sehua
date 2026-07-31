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

# 附件已失效 / 404 / Not Found（Discuz 提示页或 HTTP 文案）→「附件为空跳过」
ATTACHMENT_NOT_FOUND_MARKERS = (
    "附件不存在或无法读入",
    "附件不存在",
    "附件已删除",
    "附件已被删除",
    "该附件不存在",
    "无法找到附件",
    "找不到附件",
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

# 文件名含「目录树」：明确跳过，不下、不试算、不垫底轮询
DIRECTORY_TREE_NAME_MARKERS = (
    "目录树",
    "目錄樹",
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
    # 命中「今天下载…请明天再来」等日限提示（与无权同 denied，但可单独入附件队列）
    daily_limited: bool = False
    # 种子附件 HTTP 200 但 body=0（空壳种子）→ 跳过「种子大小为0」，勿重试
    empty_torrent: bool = False
    # 附件 Not Found / 404 / 空壳文件 → 跳过「附件为空跳过」
    empty_attachment: bool = False


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


def is_attachment_not_found(html: str) -> bool:
    """附件下载是否落到 404 / Not Found /「附件不存在」提示页。"""
    text = html or ""
    if not text:
        return False
    low = text.lower()
    if "not found" in low:
        return True
    if any(marker in text for marker in ATTACHMENT_NOT_FOUND_MARKERS):
        return True
    # nginx/Discuz 空壳 404 页（标题含 404；勿用正文 aid=404 误伤）
    if re.search(r"<title[^>]*>[^<]*\b404\b", text, re.I):
        return True
    return False


def is_attachment_denied(html: str) -> bool:
    """附件下载响应或帖内是否出现无权/需登录/日限提示。

    会剔除「请先登录再打赏」等非附件文案，避免 2048 全页脚本误伤。
    未登录 / 日限 /「只有特定用户可以下载」均算 denied → 占位「附件无权（占位入库）」（勿跳过）。
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


_ATTACH_ZONE_BLOCK_RE = re.compile(
    r"(?is)<(?:div|td|li|ignore_js_op)\b[^>]*"
    r"(?:class\s*=\s*[\"'][^\"']*(?:tattl|pattl|attach-card|attnm)[^\"']*[\"']|"
    r"id\s*=\s*[\"']attach[^\"']*[\"'])"
    r"[^>]*>.*?</(?:div|td|li|ignore_js_op)>",
)
_ATTACH_HREF_WINDOW_RE = re.compile(
    r"(?is).{0,240}(?:mod=attachment|action=download|job\.php\?[^\"'\s<>]*download).{0,240}"
)


def listing_shows_attach_denied(html: str) -> bool:
    """附件列表/楼主区已写明无权——无需逐个下载即可占位。

    只认明确无权文案；**不含**「阅读权限: N」（那只是门槛提示，账号可能够下）。
    """
    if thread_body_shows_attach_denied(html):
        return True
    raw = html or ""
    if not raw:
        return False
    chunks: list[str] = [m.group(0) for m in _ATTACH_ZONE_BLOCK_RE.finditer(raw)]
    if not chunks:
        chunks = [m.group(0) for m in _ATTACH_HREF_WINDOW_RE.finditer(raw)]
    if not chunks:
        return False
    blob = "\n".join(chunks).replace("请先登录再打赏", "")
    if any(m in blob for m in THREAD_BODY_ATTACH_DENIED_MARKERS):
        return True
    if any(m in blob for m in ATTACHMENT_DENIED_MARKERS):
        return True
    if any(m in blob for m in ATTACHMENT_LOGIN_MARKERS):
        return True
    if any(m in blob for m in ATTACHMENT_LIMIT_MARKERS):
        return True
    return False


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
    # .torrent；发帖截断常见 .torren（缺末尾 t，tid 3615372）
    if re.search(r"\.torrent?$", lower):
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


def is_directory_tree_attachment_name(name: str) -> bool:
    """文件名含「目录树」→ 附件下载硬跳过（任意类型）。"""
    raw = name or ""
    return any(marker in raw for marker in DIRECTORY_TREE_NAME_MARKERS)


def _looks_like_directory_attachment(name: str, *, kind: str = "txt") -> bool:
    """仅对 txt 判断目录类；zip/rar 文件名常带「文件夹」仍是资源包。

    「目录树」另见 is_directory_tree_attachment_name（硬跳过，不进轮询）。
    """
    if kind != "txt":
        return False
    if is_directory_tree_attachment_name(name):
        return True
    lower = name.lower()
    if lower.endswith("/") or lower.endswith("\\"):
        return True
    return any(marker in name or marker in lower for marker in DIRECTORY_ATTACHMENT_MARKERS)


_EMAIL_PROTECTED_RE = re.compile(r"\[?\s*email\s*protected\s*\]?", re.I)


def _merge_cf_decoded_name(decoded: str, visible: str) -> str:
    """把 CF 解码前缀与锚点可见尾巴拼成完整附件名。

    常见两种：
    - 整名都在 data-cfemail 里 → 可见区只有 [email protected]
    - 只混淆 @ 前缀 → 可见区为「[email protected] 国产传媒合集.txt」
    """
    decoded = (decoded or "").strip()
    visible = (visible or "").replace("\xa0", " ").strip()
    if not decoded:
        return visible
    if not visible:
        return decoded
    if _EMAIL_PROTECTED_RE.search(visible):
        name = _EMAIL_PROTECTED_RE.sub(decoded, visible, count=1)
    elif decoded in visible:
        name = visible
    else:
        name = f"{decoded}{visible}"
    return re.sub(r"\s+", " ", name).strip()


def _anchor_attachment_name(a) -> str:
    """附件显示名；含 @ 时 Discuz/CF 常写成 [email protected]，需解 data-cfemail。"""
    decoded = ""
    find_all = getattr(a, "find_all", None)
    if callable(find_all):
        for el in find_all(True):
            enc = ""
            if hasattr(el, "get"):
                enc = (el.get("data-cfemail") or "").strip()
            if enc:
                decoded = decode_cf_email(enc).strip()
                if decoded:
                    break
    title = (a.get("title") or "").strip() if hasattr(a, "get") else ""
    if title and _attachment_kind(title):
        return title
    name = a.get_text(" ", strip=True) if hasattr(a, "get_text") else ""
    name = (name or "").replace("\xa0", " ").strip()
    if decoded:
        return _merge_cf_decoded_name(decoded, name)
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
                    # 文件名无后缀 / 截断后缀：邻近 torrent.gif / alt=torrent 推断
                    parent = a.find_parent("div", class_="attach-card")
                    scope = parent if parent is not None else (
                        a.find_parent("ignore_js_op")
                        or a.find_parent("div", class_="tattl")
                        or a.find_parent("div", class_="pattl")
                        or a.parent
                    )
                    if scope is not None:
                        icon = scope.select_one(
                            "img[src*='torrent'], img[alt*='torrent']"
                        )
                        # 同段文字旁的 filetype/torrent.gif（色花转帖常见）
                        if icon is None and a.parent is not None:
                            icon = a.parent.find_previous(
                                "img", src=re.compile(r"torrent", re.I)
                            )
                        if icon is not None:
                            if not re.search(r"\.torrent?$", name, re.I):
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
        plain = re.sub(r"<[^>]+>", "", inner).replace("\xa0", " ").strip()
        cf = re.search(r'data-cfemail=["\']([0-9a-fA-F]+)["\']', inner, re.I)
        if cf:
            name = _merge_cf_decoded_name(decode_cf_email(cf.group(1)), plain)
        else:
            name = plain
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


def _attach_name_priority(name: str, *, preferred_link: str | None = None) -> int:
    """越小越优先。

    115ed2k / ed2k 与 115sha / sha1 是两类链，勿混优先级：
    - 电驴板：优先 115ed2k·ed2k·98·一分也是爱；115sha/sha1 名降权（避免先下到纯 sha 语料）
    - 其它板：115ed2k·ed2k·98·一分也是爱·含 115 仍优先；sha1 名不额外加权
    """
    raw = name or ""
    n = raw.casefold()
    pref = (preferred_link or "ed2k").strip().lower()
    if "ed2k" in n or "电驴" in raw:
        return 0
    if "98" in n or "一分也是爱" in raw:
        return 0
    is_sha_name = "115sha" in n or bool(
        re.search(r"(?<![a-z0-9])sha1(?![a-z0-9])", n)
    )
    if is_sha_name:
        return 3 if pref in {"", "ed2k"} else 1
    if "115" in n:
        return 0
    return 1


def _attach_kind_order(preferred_link: str | None) -> dict[str, int]:
    pref = (preferred_link or "ed2k").strip().lower()
    if pref in {"magnet", "both"}:
        return _ATTACH_ORDER_MAGNET
    return _ATTACH_ORDER_ED2K


def filter_tail_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
) -> list[DownloadAttachment]:
    """txt / excel / doc / zip / rar：115ed2k/98/一分也是爱 文件名优先，再按类型排序逐个轮询。"""
    candidates = [
        item
        for item in attachments
        if item.kind in ("txt", "excel", "doc", "zip", "rar")
        and not is_directory_tree_attachment_name(item.name)
    ]
    filtered = [
        item
        for item in candidates
        if not _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    if not filtered:
        # 仅剩普通目录类 txt 时可回退；「目录树」永不进入
        filtered = [
            item
            for item in candidates
            if item.kind == "txt" and not is_directory_tree_attachment_name(item.name)
        ]
    order = {"txt": 0, "excel": 1, "doc": 2, "zip": 3, "rar": 4}
    filtered.sort(
        key=lambda a: (
            _attach_name_priority(a.name, preferred_link="ed2k"),
            order.get(a.kind, 9),
            a.name,
        )
    )
    lim = max(1, min(int(limit), MAX_ATTACHMENTS_PER_THREAD))
    return filtered[:lim]


def filter_torrent_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
) -> list[DownloadAttachment]:
    filtered = [
        item
        for item in attachments
        if item.kind == "torrent" and not is_directory_tree_attachment_name(item.name)
    ]
    filtered.sort(
        key=lambda a: (_attach_name_priority(a.name, preferred_link="magnet"), a.name)
    )
    lim = max(1, min(int(limit), MAX_ATTACHMENTS_PER_THREAD))
    if len(filtered) <= lim:
        return filtered
    return filtered[:lim]


def filter_all_link_attachments(
    attachments: list[DownloadAttachment],
    *,
    limit: int = MAX_ATTACHMENTS_PER_THREAD,
    preferred_link: str | None = None,
) -> list[DownloadAttachment]:
    """全部可抽链附件：先按文件名优先级，再按板块主链类型，逐个轮询。

    文件名：115ed2k/ed2k 与 115sha/sha1 分开（电驴板勿先下 sha 名）。
    - 电驴板：txt → zip/rar → excel/doc → torrent
    - 磁力/双链：torrent → excel/doc/txt → zip/rar
    - 文件名含「目录树」：硬跳过（不下、不试算）
    - 其它目录类 txt（含「目录」「文件夹」等）排在同批末尾，仍纳入轮询
    每下完一个有链附件即试算；合格则停；不合格必须继续直到判完或合格。
    """
    candidates = [
        item
        for item in attachments
        if item.kind in ("txt", "excel", "doc", "zip", "rar", "torrent")
        and not is_directory_tree_attachment_name(item.name)
    ]
    primary = [
        item
        for item in candidates
        if item.kind == "torrent"
        or not _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    # 其它目录类 txt 垫底仍要判断（不含「目录树」）
    directory_txt = [
        item
        for item in candidates
        if item.kind == "txt"
        and _looks_like_directory_attachment(item.name, kind=item.kind)
    ]
    if not primary and not directory_txt:
        primary = [item for item in candidates if item.kind == "txt"]
    order = _attach_kind_order(preferred_link)

    def _sort_key(a: DownloadAttachment) -> tuple:
        return (
            _attach_name_priority(a.name, preferred_link=preferred_link),
            order.get(a.kind, 9),
            a.name,
        )

    primary.sort(key=_sort_key)
    directory_txt.sort(key=_sort_key)
    filtered = primary + directory_txt
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


def pick_magnet_attachment_kind(base_url: str, html: str, *, title: str = "") -> str:
    """磁力板：有种子优先下种子；否则 Excel/文本；BT种子标题强制偏好 torrent。"""
    atts = extract_download_attachments(base_url, html)
    title_l = title or ""
    prefer_torrent = (
        "BT种子" in title_l
        or "【BT" in title_l
        or "bt种子" in title_l.lower()
    )
    has_torrent = bool(filter_torrent_attachments(atts))
    if prefer_torrent and has_torrent:
        return "torrent"
    if has_torrent and not any(a.kind in ("excel", "doc") for a in atts):
        return "torrent"
    if any(a.kind in ("excel", "doc") for a in atts) and not prefer_torrent:
        return "txt_tail"
    if has_torrent:
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
