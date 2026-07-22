"""Lightweight Discuz page gates (aligned with ed2k detail_spider markers)."""

from __future__ import annotations

import re

# 目标链探测：须可解析入库的完整形态（勿把缺 hash 的半截 ed2k 当有链）
ED2K_RE = re.compile(
    r"ed2k://\|file\|[^\|]+\|\d+\|[A-Fa-f0-9]{32}\|",
    re.I,
)
MAGNET_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?:[A-Fa-f0-9]{40}|[a-zA-Z2-7]{32})",
    re.I,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
POSTMESSAGE_RE = re.compile(
    r"""id=['"]postmessage_[^'"]*['"][^>]*>(.*?)</div>""",
    re.I | re.S,
)
_FID_RE = re.compile(
    r"(?:fid=|/forum-)(\d+)|forum\.php\?[^\"'\s<>]*fid=(\d+)",
    re.I,
)

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
# 版主/管理员屏蔽（Discuz locked 框：「该帖被管理员或版主屏蔽」）
MODERATOR_BLOCKED_MARKERS = (
    "该帖被管理员或版主屏蔽",
    "被管理员或版主屏蔽",
    "主题被屏蔽",
    "本主题已被屏蔽",
)
# 作者被禁/删：正文自动屏蔽（Discuz locked：「作者被禁止或删除 内容自动屏蔽」）
# 勿单独匹配「内容自动屏蔽」——其它 locked/提示也可能带这四字，易误伤正常帖
AUTHOR_BANNED_MARKERS = (
    "作者被禁止或删除 内容自动屏蔽",
    "作者被禁止或删除",
)

REPLY_MARKERS = (
    "游客，如果您要查看本帖隐藏内容请回复",
    "如果您要查看本帖隐藏内容请回复",
    "隐藏内容请回复",
    "本帖隐藏的内容需要回复",
    "需要回复才可以浏览",
    "需要回复才能查看",
    "回复后才能查看隐藏",
    "回复之后才能看到",
)
# Discuz 模板常写成「请<a href>回复</a>」，中间夹标签/空白
_REPLY_GATE_RE = re.compile(
    r"(?:如果您要查看本帖)?隐藏内容请\s*(?:<[^>]+>\s*)*回复"
    r"|隐藏内容需要回复"
    r"|需要回复才(?:可以|能)(?:浏览|查看)"
    r"|回复后才能查看",
    re.I,
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
    r"(?:https?://)?(?:"
    r"pan\.xunlei\.com|"
    r"pan\.baidu\.com|"
    r"(?:www\.)?aliyundrive\.com|"
    r"(?:www\.)?alipan\.com|"
    r"pan\.quark\.cn|"
    r"cloud\.189\.cn|"
    r"(?:www\.)?115\.com/s/|"
    r"(?:www\.)?115cdn\.com/s/|"
    r"(?:www\.)?mypikpak\.com/s/"
    r")",
    re.I,
)
# 115 直链分享：115://文件名|字节数|hash|hash
RE_115_SHA = re.compile(
    r"115://[^\s<>\"'|]+\|\d+\|[A-Fa-f0-9]{32,64}\|[A-Fa-f0-9]{32,64}",
    re.I,
)
# 115 网盘分享页：115.com/s/... 或 115cdn.com/s/...（含访问码参数亦可）
RE_115_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:115\.com|115cdn\.com)/s/[A-Za-z0-9]+",
    re.I,
)
# 迅雷云盘分享：pan.xunlei.com/s/...
RE_XUNLEI_SHARE = re.compile(
    r"(?:https?://)?(?:pan\.)?xunlei\.com/s/[A-Za-z0-9_-]+",
    re.I,
)
# PikPak 分享：mypikpak.com/s/...
RE_PIKPAK_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?mypikpak\.com/s/[A-Za-z0-9_-]+",
    re.I,
)
# 百度网盘分享：pan.baidu.com/s/... 或 yun.baidu.com/s/...
RE_BAIDU_SHARE = re.compile(
    r"(?:https?://)?(?:pan|yun)\.baidu\.com/s/[A-Za-z0-9_-]+",
    re.I,
)
SOFT_AD_TITLE_HINTS = ("名人名言", "请稍候", "Just a moment")
GENERIC_TITLES = frozenset({"提示信息", "提示", "手机版", "请稍候"})
MOBILE_SHELL_TITLES = frozenset({"手机版", "请稍候…", "请稍候"})

# Discuz 主题已删 / tid 无效
MISSING_THREAD_MARKERS = (
    "没有找到帖子",
    "没有找到主题",
    "主题不存在",
    "抱歉，指定的主题不存在",
    "指定的主题不存在",
    "帖子不存在",
    "内容不存在或已被删除",
    "抱歉，本帖不存在",
)

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
    """板块目标链：ed2k 板同时接受电驴与磁力（常见混发）；magnet 板仍只要磁力。

    ed2k 板另认 115 网盘分享页（分享码资源可入库）。
    """
    from parsers.ed2k import normalize_ed2k_corpus
    from parsers.magnet import normalize_magnet_corpus

    raw = text or ""
    blob = normalize_ed2k_corpus(normalize_magnet_corpus(raw))
    if link_kind == "ed2k":
        return bool(
            ED2K_RE.search(blob)
            or MAGNET_RE.search(blob)
            or RE_115_SHARE.search(blob)
        )
    if link_kind == "magnet":
        return bool(MAGNET_RE.search(blob))
    return bool(
        ED2K_RE.search(blob) or MAGNET_RE.search(blob) or RE_115_SHARE.search(blob)
    )


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


def should_skip_as_115sha_only(text: str) -> bool:
    """附件语料含 115sha，且没有可入库的 magnet/ed2k 时才整帖跳过。

    同一压缩包内常同时有 Excel 磁力与 sha1.txt；有磁力则不应因 115sha 丢弃。
    """
    if not has_115_sha_link(text):
        return False
    low = (text or "").lower()
    if "magnet:" in low or "ed2k://" in low:
        return False
    return True


def has_115_share_link(text: str) -> bool:
    """识别 115 网盘分享页链接：115.com/s/xxxx（含提取码参数亦可）。"""
    return bool(RE_115_SHARE.search(text or ""))


def has_xunlei_share_link(text: str) -> bool:
    """识别迅雷云盘分享：pan.xunlei.com/s/..."""
    return bool(RE_XUNLEI_SHARE.search(text or ""))


def has_pikpak_share_link(text: str) -> bool:
    """识别 PikPak 分享：mypikpak.com/s/..."""
    return bool(RE_PIKPAK_SHARE.search(text or ""))


def has_baidu_share_link(text: str) -> bool:
    """识别百度网盘分享：pan.baidu.com/s/..."""
    return bool(RE_BAIDU_SHARE.search(text or ""))


def title_is_xunlei_cloud_without_ed2k_magnet(title: str) -> bool:
    """标题标明迅雷云盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    t = (title or "").strip()
    if not t:
        return False
    if "迅雷云盘" not in t and "迅雷网盘" not in t and not re.search(r"迅雷\s*云盘", t):
        return False
    lower = t.lower()
    if any(x in lower for x in ("ed2k", "magnet", "磁力", "电驴", "种子", "torrent")):
        return False
    return True


def title_is_pikpak_without_ed2k_magnet(title: str) -> bool:
    """标题标明 PikPak，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    t = (title or "").strip()
    if not t:
        return False
    lower = t.lower()
    if "pikpak" not in lower and "pik pak" not in lower:
        return False
    if any(x in lower for x in ("ed2k", "magnet", "磁力", "电驴", "种子", "torrent")):
        return False
    return True


def title_is_baidu_pan_without_ed2k_magnet(title: str) -> bool:
    """标题标明百度网盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    t = (title or "").strip()
    if not t:
        return False
    if "百度网盘" not in t and "百度云" not in t and not re.search(r"百度\s*网盘", t):
        return False
    lower = t.lower()
    if any(x in lower for x in ("ed2k", "magnet", "磁力", "电驴", "种子", "torrent")):
        return False
    return True


def title_is_115_share_without_ed2k_magnet(title: str) -> bool:
    """标题标明 115 分享/分享码/网盘分享，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    t = (title or "").strip()
    if not t:
        return False
    # 115分享 / 115分享码 / 115网盘分享 / 115 分享链接
    if not re.search(r"115\s*(?:网盘)?\s*分享(?:码|链接)?", t):
        return False
    lower = t.lower()
    if any(x in lower for x in ("ed2k", "magnet", "磁力", "电驴", "种子", "torrent")):
        return False
    return True


def title_is_115sha_without_ed2k_magnet(title: str) -> bool:
    """标题标明 115sha，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    t = (title or "").strip()
    if not t:
        return False
    lower = re.sub(r"\s+", "", t.lower())
    has_115 = "115sha" in lower or bool(re.search(r"\[?\s*115\s*sha", t, re.I))
    if not has_115:
        return False
    if any(x in lower for x in ("ed2k", "magnet")):
        return False
    if "磁力" in t or "电驴" in t:
        return False
    return True


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
    """站点软文 / R18 安全壳 / CF 中间页。

    真帖（有一楼 postmessage）即使较短、页脚未抓全，也不得当成软文壳。
    """
    if not html:
        return True
    # 安全壳脚本（名人名言 / R18 门）
    if "var safeid" in html or "static/safe/" in html.lower():
        return True
    title = page_title(html)
    if any(h in title for h in SOFT_AD_TITLE_HINTS):
        return True
    # 无 Discuz 页脚的短页：仅当也无一楼正文时才视为中间页
    # （旧逻辑只要 <5KB 且无 Powered by 就判软文，会误伤「需回复」等真帖片段）
    if (
        "Powered by Discuz" not in html
        and len(html) < 5000
        and not has_thread_post_body(html)
    ):
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


def is_missing_thread(html: str, title: str = "") -> bool:
    """识别 Discuz「没有找到帖子 / 主题不存在」等空洞页。"""
    if not html and not title:
        return False
    tit = (title or page_title(html) or "").strip()
    blob = f"{tit}\n{html or ''}"
    if any(m in blob for m in MISSING_THREAD_MARKERS):
        return True
    # 极短提示页且无正文
    if len(html or "") < 12000 and "postmessage_" not in (html or "") and (
        "提示信息" in tit or normalize_title_core(tit) in GENERIC_TITLES
    ):
        # 避免把登录/权限提示页误当成不存在（那些有专门分支）
        if any(m in blob for m in LOGIN_MARKERS) or any(
            m in blob for m in ACCESS_DENIED_MARKERS
        ):
            return False
        return True
    return False


def is_thread_moderator_blocked(html: str) -> bool:
    """管理员/版主屏蔽：正文 locked，永久不可抓。"""
    if not html:
        return False
    if any(m in html for m in MODERATOR_BLOCKED_MARKERS):
        return True
    body = re.sub(r"<[^>]+>", "\n", html)
    return any(m in body for m in MODERATOR_BLOCKED_MARKERS)


def is_thread_author_banned(html: str) -> bool:
    """作者被禁止或删除，内容自动屏蔽。

    必须明确出现「作者被禁止」；若一楼已有有效正文/链接，视为正常帖（避免误跳过）。
    """
    if not html:
        return False
    plain = re.sub(r"<[^>]+>", "\n", html)
    locked_hit = bool(
        re.search(
            r'class=["\']locked["\'][^>]*>[^<]*作者被禁止',
            html,
            re.I,
        )
    )
    text_hit = any(m in html or m in plain for m in AUTHOR_BANNED_MARKERS)
    if not (locked_hit or text_hit):
        return False

    text = post_text(html)
    if has_target_link(text, "both"):
        return False

    # 去掉锁定提示后若仍有足够正文，说明并非「内容已屏蔽」
    cleaned = text
    for m in (*AUTHOR_BANNED_MARKERS, "内容自动屏蔽", "提示:", "提示："):
        cleaned = cleaned.replace(m, "")
    cleaned = re.sub(r"\s+", "", cleaned)
    if len(cleaned) >= 40:
        return False
    return True


def is_reply_required_post(html: str) -> bool:
    """需回复才看隐藏内容（调用方：满龄/非龄期板 → 占位；龄期未满 → 先跳过）。

    线上文案示例：``poilly，如果您要查看本帖隐藏内容请<a>回复</a>``
    （登录用户名 / 游客前缀均可；「请」与「回复」常被链接拆开。）
    """
    if not html:
        return False
    if any(m in html for m in REPLY_MARKERS):
        return True
    if _REPLY_GATE_RE.search(html):
        return True
    # 去标签后：请<a>回复</a> → 「请 回复」，再压掉空白便于匹配
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain)
    plain_compact = plain.replace(" ", "")
    if any(m in plain for m in REPLY_MARKERS) or any(m in plain_compact for m in REPLY_MARKERS):
        return True
    if (
        "隐藏内容" in plain
        and "如果您要查看本帖" in plain
        and ("请回复" in plain_compact or "请回复" in plain)
    ):
        return True
    if "showhide" in html.lower() and (
        "请回复" in plain_compact or "回复后才能" in plain_compact
    ):
        return True
    return False


def is_purchase_required_post(html: str) -> bool:
    if not html or is_reply_required_post(html):
        return False
    blob = f"{html}\n{post_text(html)}"
    return any(m in blob for m in PURCHASE_MARKERS)


def is_non_target_cloud_share(*, link_kind: str, text: str) -> bool:
    """ED2K 板：只有网盘分享、无电驴/磁力/115分享。"""
    if link_kind != "ed2k":
        return False
    from parsers.ed2k import normalize_ed2k_corpus
    from parsers.magnet import normalize_magnet_corpus

    blob = normalize_ed2k_corpus(normalize_magnet_corpus(text or ""))
    if ED2K_RE.search(blob) or MAGNET_RE.search(blob) or RE_115_SHARE.search(blob):
        return False
    return bool(CLOUD_SHARE_RE.search(text or ""))


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


def extract_board_fid(html: str, preferred_fid: int | None = None) -> int | None:
    """从帖页抽真实 fid；若 preferred 出现在页内则优先（避免侧栏/热帖链抢走）。"""
    if not html:
        return None
    found: list[int] = []
    for m in _FID_RE.finditer(html):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        fid = int(raw)
        if 1 <= fid <= 9999 and fid not in found:
            found.append(fid)
    if not found:
        return None
    pref = int(preferred_fid) if preferred_fid else 0
    if pref and pref in found:
        return pref
    return found[0]


def extract_thread_typeid(html: str, board_fid: str) -> str | None:
    """从帖页抽 typeid；只接受带 fid 的链接，或该板白名单子版。"""
    if not html:
        return None
    from parsers.boards import BOARD_POLICIES, board_unit_key

    fid = str(board_fid or "").strip()
    if fid:
        m = re.search(
            rf"fid={re.escape(fid)}(?:&amp;|&)[^\"'<>]{{0,120}}?typeid=(\d+)",
            html,
            re.I,
        )
        if m and board_unit_key(fid, m.group(1)) in BOARD_POLICIES:
            return m.group(1)
        m = re.search(
            rf"typeid=(\d+)(?:&amp;|&)[^\"'<>]{{0,120}}?fid={re.escape(fid)}",
            html,
            re.I,
        )
        if m and board_unit_key(fid, m.group(1)) in BOARD_POLICIES:
            return m.group(1)
        m = re.search(r"filter=typeid(?:&amp;|&)typeid=(\d+)", html, re.I)
        if m and board_unit_key(fid, m.group(1)) in BOARD_POLICIES:
            return m.group(1)
        for tm in re.finditer(r"typeid=(\d+)", html, re.I):
            tid = tm.group(1)
            if board_unit_key(fid, tid) in BOARD_POLICIES:
                return tid
    return None


def resolve_thread_board_meta(
    html: str,
    *,
    fallback_key: int | str = "",
    fallback_name: str = "",
) -> tuple[str, str]:
    """从帖页解析二级板块 key / 展示名；解析不到则保留 fallback。

    用于已入库重爬等场景：库里可能是旧纯 fid 或空名，需按帖页回写「主板块 · 子分类」。
    """
    from parsers.boards import BOARD_POLICIES, board_unit_key, get_board_policy, parse_board_key

    fb_key = str(fallback_key or "").strip()
    fb_name = (fallback_name or "").strip()
    if fb_name.lower().startswith("fid-") or fb_name.lower().startswith("fid "):
        fb_name = ""
    fb_fid, fb_tid = parse_board_key(fb_key)

    fid = extract_board_fid(html or "", preferred_fid=fb_fid or None)
    if not fid:
        fid = fb_fid
    if not fid:
        return fb_key, fb_name

    typeid = extract_thread_typeid(html or "", str(fid))
    if typeid and board_unit_key(fid, typeid) not in BOARD_POLICIES:
        typeid = None
    # 帖页抽不到合法子版时：同 fid 的入库/队列子版 key 继续用
    if not typeid and fb_fid == fid and fb_tid:
        typeid = fb_tid

    if typeid:
        key = board_unit_key(fid, typeid)
    elif fb_fid == fid and ":" in fb_key:
        key = fb_key
    else:
        key = str(fid)

    pol = get_board_policy(key)
    name = (pol.name or "").strip() or fb_name or (pol.board_name or "").strip()
    if name.lower().startswith("fid-") or name.lower().startswith("fid "):
        name = fb_name or (pol.board_name or "").strip()
    return pol.key, name


def thread_typeid_mismatch(html: str, board_fid: str, required_typeid: str | None) -> bool:
    if not required_typeid:
        return False
    actual = extract_thread_typeid(html, str(board_fid))
    return actual is not None and actual != str(required_typeid)


def looks_like_attachment_zone(html: str) -> bool:
    """是否有可解析的资源附件（txt/zip/rar/torrent）。预览图不算。"""
    if not html:
        return False
    from parsers.attachments import extract_download_attachments

    return bool(extract_download_attachments("", html))
