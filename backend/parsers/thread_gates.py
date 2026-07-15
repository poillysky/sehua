"""Lightweight Discuz page gates (aligned with ed2k detail_spider markers)."""

from __future__ import annotations

import re

ED2K_RE = re.compile(r"ed2k://\|file\|", re.I)
MAGNET_RE = re.compile(r"magnet:\?xt=urn:btih:", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
POSTMESSAGE_RE = re.compile(r'id="postmessage_[^"]*"[^>]*>(.*?)</div>', re.I | re.S)

LOGIN_MARKERS = (
    "请先登录后",
    "您需要登录后",
    "需要登录后才能查看",
    "此帖仅对会员开放",
    "只有会员才能查看",
    "没有权限查看此帖",
)
ACCESS_DENIED_MARKERS = (
    "本帖要求阅读权限",
    "阅读权限高于",
    "阅读权限不足",
    "需要更高的阅读权限",
    "您无权访问该帖",
    "没有权限查看此帖",
)
REPLY_MARKERS = (
    "游客，如果您要查看本帖隐藏内容请回复",
    "如果您要查看本帖隐藏内容请回复",
    "隐藏内容请回复",
)
PURCHASE_MARKERS = (
    "本主题需向作者支付",
    "需向作者支付",
    "金钱 才能浏览",
    "积分 才能浏览",
    "购买主题",
    "本帖售价",
    "此帖售价",
    "您必须先购买",
    "付费主题",
    "您还没有购买此主题",
)
CLOUD_SHARE_RE = re.compile(
    r"https?://(?:"
    r"pan\.xunlei\.com|"
    r"pan\.baidu\.com|"
    r"(?:www\.)?aliyundrive\.com|"
    r"pan\.quark\.cn|"
    r"cloud\.189\.cn"
    r")",
    re.I,
)
# 115 直链分享：115://文件名|字节数|hash|hash
RE_115_SHA = re.compile(
    r"115://[^\s<>\"'|]+\|\d+\|[A-Fa-f0-9]{32,64}\|[A-Fa-f0-9]{32,64}",
    re.I,
)
SOFT_AD_TITLE_HINTS = ("名人名言", "请稍候", "Just a moment")
GENERIC_TITLES = frozenset({"提示信息", "提示", "手机版", "请稍候"})
MOBILE_SHELL_TITLES = frozenset({"手机版", "请稍候…", "请稍候"})


def page_title(html: str) -> str:
    m = TITLE_RE.search(html or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def normalize_title_core(title: str) -> str:
    """去掉站点后缀，便于识别「提示信息 - 论坛名」一类伪标题。"""
    t = re.sub(r"\s+", " ", (title or "").strip())
    if not t:
        return ""
    # Discuz 常见：「标题 - 论坛名」「标题 | 论坛名」
    for sep in (" - ", " – ", " — ", " | ", "｜"):
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    return t


def post_text(html: str) -> str:
    chunks = POSTMESSAGE_RE.findall(html or "")
    if not chunks:
        return ""
    text = "\n".join(chunks)
    try:
        from parsers.content import restore_cloudflare_emails

        text = restore_cloudflare_emails(text)
    except Exception:
        pass
    text = re.sub(r"<[^>]+>", "\n", text)
    return re.sub(r"\s+", " ", text).strip()


def has_thread_post_body(html: str) -> bool:
    return bool(POSTMESSAGE_RE.search(html or ""))


def is_mobile_thread_shell(html: str) -> bool:
    """识别手机版空壳帖页（无 postmessage 正文）。"""
    if not html:
        return False
    if has_thread_post_body(html):
        return False
    title = page_title(html)
    if title in MOBILE_SHELL_TITLES or title in GENERIC_TITLES:
        return True
    lowered = html.lower()
    if "mobile=2" in lowered and len(html) < 25000:
        return True
    if len(html) < 12000 and ("viewthread" in lowered or "thread-" in lowered):
        return "forumdisplay" not in lowered
    return False

def has_target_link(text: str, link_kind: str) -> bool:
    """板块目标链：ed2k 板同时接受电驴与磁力（常见混发）；magnet 板仍只要磁力。"""
    blob = text or ""
    if link_kind == "ed2k":
        return bool(ED2K_RE.search(blob) or MAGNET_RE.search(blob))
    if link_kind == "magnet":
        return bool(MAGNET_RE.search(blob))
    return bool(ED2K_RE.search(blob) or MAGNET_RE.search(blob))


def has_115_sha_link(text: str) -> bool:
    """识别 115sha 直链：115://文件名|size|hash|hash。

    附件语料常把长链拆成多行，匹配前去掉空白再搜。
    """
    if not text:
        return False
    if RE_115_SHA.search(text):
        return True
    compact = re.sub(r"\s+", "", text)
    return compact != text and bool(RE_115_SHA.search(compact))


def title_recognizable(title: str) -> bool:
    raw = (title or "").strip()
    if len(raw) < 2:
        return False
    t = normalize_title_core(raw)
    if len(t) < 2:
        return False
    if t in GENERIC_TITLES or raw in GENERIC_TITLES:
        return False
    # 「提示信息xxx」等系统页
    if any(t == g or t.startswith(g) for g in GENERIC_TITLES):
        return False
    if any(h in raw or h in t for h in SOFT_AD_TITLE_HINTS):
        return False
    return True


def is_safe_or_soft_shell(html: str) -> bool:
    if not html:
        return True
    if len(html) < 12000 and ("var safeid" in html or "static/safe/" in html.lower()):
        return True
    title = page_title(html)
    if any(h in title for h in SOFT_AD_TITLE_HINTS):
        return True
    if "Powered by Discuz" not in html and len(html) < 5000:
        return True
    return False


def is_thread_login_required(html: str) -> bool:
    if is_thread_access_denied(html):
        return False
    text = post_text(html)
    if has_target_link(text, "both"):
        return False
    if len(text) > 200:
        return False
    if any(m in text for m in LOGIN_MARKERS):
        return True
    if len(text) < 80 and "登录" in text and "发表回复" not in text:
        return True
    return False


def is_thread_access_denied(html: str) -> bool:
    if not html:
        return False
    body = re.sub(r"<[^>]+>", "\n", html)
    if not any(m in body for m in ACCESS_DENIED_MARKERS):
        return False
    text = post_text(html)
    if has_target_link(text, "both"):
        return False
    title = normalize_title_core(page_title(html))
    if title in GENERIC_TITLES or title.startswith("提示"):
        return True
    return "postmessage_" not in html


def is_reply_required_post(html: str) -> bool:
    if not html:
        return False
    if any(m in html for m in REPLY_MARKERS):
        return True
    return "隐藏内容" in html and "请回复" in html and "如果您要查看本帖" in html


def is_purchase_required_post(html: str) -> bool:
    if not html or is_reply_required_post(html):
        return False
    blob = f"{html}\n{post_text(html)}"
    return any(m in blob for m in PURCHASE_MARKERS)


def is_non_target_cloud_share(*, link_kind: str, text: str) -> bool:
    """ED2K 板：只有网盘分享、无电驴/磁力。"""
    if link_kind != "ed2k":
        return False
    blob = text or ""
    if ED2K_RE.search(blob) or MAGNET_RE.search(blob):
        return False
    return bool(CLOUD_SHARE_RE.search(blob))


def title_implies_resource(title: str, link_kind: str) -> bool:
    t = (title or "").lower()
    if link_kind == "ed2k":
        return any(
            x in t
            for x in (
                "ed2k",
                "115",
                "98t",
                "电驴",
                "magnet",
                "磁力",
                "磁链",
                "种子",
                "torrent",
                "bt",
            )
        )
    if link_kind == "magnet":
        return any(x in t for x in ("magnet", "磁力", "磁链", "种子", "torrent", "bt"))
    if link_kind == "both":
        return any(
            x in t
            for x in (
                "ed2k",
                "115",
                "98t",
                "电驴",
                "magnet",
                "磁力",
                "磁链",
                "种子",
                "torrent",
                "bt",
            )
        )
    return False


def is_genuine_non_resource(*, html: str, title: str, link_kind: str, text: str) -> bool:
    if has_target_link(text, link_kind):
        return False
    if is_safe_or_soft_shell(html):
        return False
    if len(html or "") < 8000:
        return False
    if title_implies_resource(title, link_kind):
        return False
    if is_non_target_cloud_share(link_kind=link_kind, text=text):
        return False
    return True


def extract_thread_typeid(html: str, board_fid: str) -> str | None:
    if not html or not board_fid:
        return None
    pattern = re.compile(
        rf"fid={re.escape(str(board_fid))}(?:&amp;|&)[^\"'<>]*?typeid=(\d+)",
        re.I,
    )
    m = pattern.search(html)
    return m.group(1) if m else None


def thread_typeid_mismatch(html: str, board_fid: str, required_typeid: str | None) -> bool:
    if not required_typeid:
        return False
    actual = extract_thread_typeid(html, str(board_fid))
    return actual is not None and actual != str(required_typeid)


def looks_like_attachment_zone(html: str) -> bool:
    if not html:
        return False
    markers = (
        "attach_",
        "aid=",
        ".torrent",
        ".txt",
        ".zip",
        ".rar",
        "附件",
        "download.php",
    )
    return any(m in html for m in markers)
