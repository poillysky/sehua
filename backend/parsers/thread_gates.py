"""Lightweight Discuz page gates (aligned with ed2k detail_spider markers)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# 目标链探测：须可解析入库的完整形态（勿把缺 hash 的半截 ed2k 当有链）
ED2K_RE = re.compile(
    r"ed2k://\|file\|[^\|]+\|\d+\|[A-Fa-f0-9]{32}\|",
    re.I,
)
MAGNET_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{32}|[a-zA-Z2-7]{32})",
    re.I,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
POSTMESSAGE_RE = re.compile(
    r"""id=['"]postmessage_[^'"]*['"][^>]*>(.*?)</div>""",
    re.I | re.S,
)
# PHPWind 一楼正文：#read_tpc / .tpc_content
PHPWIND_BODY_RE = re.compile(
    r"""id=['"]read_tpc['"]|class=['"][^'"]*tpc_content""",
    re.I,
)
_FID_RE = re.compile(
    r"(?:fid=|/forum-)(\d+)|forum\.php\?[^\"'\s<>]*fid=(\d+)",
    re.I,
)

# 附件区快检：无此类线索则不必 BeautifulSoup（judge 热路径）
# 勿单凭 ignore_js_op：预览图也包在里面
# 缓存用内容指纹，勿用 id(html)（GC 后 id 复用会串结果）
_ATTACH_ZONE_HINT_RE = re.compile(
    r"attach-card|\bpattl\b|\btattl\b|"
    r"attachment\.php|mod=attachment|action=download|"
    r"job\.php\?[^\"'>\s]*download|"
    r"href=[\"'][^\"']*(?:attachment|action=download|job=download)[^\"']*[\"']|"
    r"\.(?:torrent?|rar|zip|7z|txt|xlsx?|xls|docx?)\b",
    re.I,
)
_ATTACH_ZONE_FP_MEMO: dict[tuple[int, int, int, int], bool] = {}


def _attach_zone_fp(html: str) -> tuple[int, int, int, int]:
    n = len(html)
    mid = n // 2
    return (
        n,
        hash(html[:256]),
        hash(html[mid : mid + 256]),
        hash(html[-256:] if n >= 256 else html),
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
    "本内容需向作者支付",
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
# 购买价格：0=免费购买可尝试解锁；>0=付费，普通爬跳过（账号爬另做）
_PURCHASE_PRICE_RE = re.compile(
    r"(?:"
    r"(?:本内容|本主题)?需向作者支付\s*(\d+)\s*(?:金币|金錢|金钱|积分|積分|色币|色幣)?"
    r"|(?:本帖|此帖)售价\s*[:：]?\s*(\d+)"
    r"|(\d+)\s*(?:金币|金錢|金钱|积分|積分|色币|色幣)\s*才能浏览"
    r")",
    re.I,
)
_PURCHASE_BUY_HREF_RE = re.compile(
    r"""href=["']([^"']*(?:action=buytopic|(?:mod=misc[^"']*action=pay)|action=pay)[^"']*)["']""",
    re.I,
)
CLOUD_SHARE_RE = re.compile(
    r"(?:https?://)?(?:"
    r"pan\.xunlei\.com|"
    r"pan\.baidu\.com|"
    r"yun\.baidu\.com|"
    r"(?:www\.)?aliyundrive\.com|"
    r"(?:www\.)?alipan\.com|"
    r"pan\.quark\.cn|"
    r"cloud\.189\.cn|"
    r"(?:www\.)?(?:123pan|123684|123865|123912|123592)\.com|"
    r"(?:[\w-]+\.)?lanzou[a-z0-9]*\.com|"
    r"(?:www\.)?lanzoux\.com|"
    r"drive\.uc\.cn|"
    r"fast\.uc\.cn|"
    r"share\.weiyun\.com|"
    r"(?:www\.)?ctfile\.com|"
    r"(?:www\.)?ctdisk\.com|"
    r"1drv\.ms|"
    r"onedrive\.live\.com|"
    r"(?:www\.)?dropbox\.com/"
    r"(?:s|scl)/|"
    r"(?:www\.)?mediafire\.com/file/|"
    r"(?:www\.)?terabox(?:app)?\.com|"
    r"(?:www\.)?mega(?:\.co)?\.nz/|"
    r"(?:drive|docs)\.google\.com/|"
    r"(?:www\.)?mypikpak\.com/s/|"
    r"(?:www\.)?115\.com/s/|"
    r"(?:www\.)?115cdn\.com/s/"
    r")",
    re.I,
)
# 115 直链分享：115://文件名|字节数|hash|hash
# 色花【sha1】帖附件常无协议头：文件名|size|sha1|pickcode（例 fc3046937.rar）
# 文件名段必须有上限：无 | 的大磁链语料上 [^\s<>\"'|]+ 会灾难回溯，拖死判帖/健康检查。
_RE_115_SHA_BODY = (
    r"[^\s<>\"'|]{1,255}\|"
    r"\d{1,18}\|"
    r"[A-Fa-f0-9]{32,64}\|"
    r"[A-Fa-f0-9]{32,64}"
)
RE_115_SHA = re.compile(rf"(?:115://)?{_RE_115_SHA_BODY}", re.I)
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
# 夸克网盘分享：pan.quark.cn/s/...
RE_QUARK_SHARE = re.compile(
    r"(?:https?://)?(?:pan\.)?quark\.cn/s/[A-Za-z0-9_-]+",
    re.I,
)
# MEGA 分享：mega.nz/file|folder|…
RE_MEGA_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?mega(?:\.co)?\.nz/(?:file|folder|#!|embed)",
    re.I,
)
# Google Drive：drive.google.com / docs.google.com
RE_GDRIVE_SHARE = re.compile(
    r"(?:https?://)?(?:drive|docs)\.google\.com/",
    re.I,
)
# 阿里云盘
RE_ALIYUN_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:aliyundrive|alipan)\.com/(?:s|t)/[A-Za-z0-9_-]+",
    re.I,
)
# 天翼云盘
RE_TIANYI_SHARE = re.compile(
    r"(?:https?://)?cloud\.189\.cn/(?:t|web/share)(?:/|\?|#)",
    re.I,
)
# 123 云盘（含常见镜像域）
RE_PAN123_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:123pan|123684|123865|123912|123592)\.com/s/[A-Za-z0-9_-]+",
    re.I,
)
# 蓝奏云（多子域/变体域）
RE_LANZOU_SHARE = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)?(?:lanzou[a-z0-9]*|lanzoux)\.com/[A-Za-z0-9_-]+",
    re.I,
)
# UC 网盘
RE_UC_SHARE = re.compile(
    r"(?:https?://)?(?:drive|fast)\.uc\.cn/s/[A-Za-z0-9_-]+",
    re.I,
)
# 腾讯微云
RE_WEIYUN_SHARE = re.compile(
    r"(?:https?://)?share\.weiyun\.com/[A-Za-z0-9_-]+",
    re.I,
)
# 城通网盘
RE_CTFILE_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:ctfile|ctdisk)\.com/(?:f|d|file)/[A-Za-z0-9_-]+",
    re.I,
)
# OneDrive
RE_ONEDRIVE_SHARE = re.compile(
    r"(?:https?://)?(?:1drv\.ms/[A-Za-z0-9_-]+|onedrive\.live\.com/)",
    re.I,
)
# Dropbox
RE_DROPBOX_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?dropbox\.com/(?:s|scl)/[A-Za-z0-9_/%-]+",
    re.I,
)
# MediaFire
RE_MEDIAFIRE_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?mediafire\.com/file/[A-Za-z0-9]+",
    re.I,
)
# Terabox（百度国际盘）
RE_TERABOX_SHARE = re.compile(
    r"(?:https?://)?(?:www\.)?terabox(?:app)?\.com/s/[A-Za-z0-9_-]+",
    re.I,
)

# 标题含目标资源暗示：有 115 / ed2k / magnet / 磁力时，不因「百度/迅雷/夸克/度盘」
# 等裸网盘字样判跳过（【百度】【115eD2k】、【迅雷+磁力】等并存 → 继续识别）。
# 注意：勿把容量「115G / 115GB」误认成 115 资源暗示。
_TITLE_HAS_TARGET_HINT_RE = re.compile(
    r"ed2k|magnet|磁力|磁[链鏈]|电驴|電驢|种子|種子|torrent|"
    r"(?<![0-9.])115(?!(?:\.\d+)?\s*[GMTgmt][Bb]?\b)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class CloudShareSpec:
    """应跳过的网盘分享（非 115 分享码入库类）。

    判定口径（勿用正文关键词扫）：
    1) 标题只点名这一种网盘，且无 115/ed2k/磁力；
    2) 解析到的资源链只含这一种网盘 URL，且无 ed2k/磁力/115。
    115 与百度等并存 → 不判网盘资源。
    """

    key: str
    label: str
    url_re: re.Pattern[str]
    title_re: re.Pattern[str] | None = None
    try_attachments: bool = False

    def skip_tip(self, *, from_title: bool = False) -> str:
        from parsers.skip_outcomes import cloud_skip_tip

        # from_title 仅语义区分，落库统一为「{盘名}（跳过）」
        _ = from_title
        return cloud_skip_tip(self.label)


# 顺序即匹配优先级；新增网盘只加条目即可
SKIP_CLOUD_SHARE_SPECS: tuple[CloudShareSpec, ...] = (
    CloudShareSpec(
        "xunlei",
        "迅雷云盘",
        RE_XUNLEI_SHARE,
        # 裸「迅雷」也算（【迅雷】帖）；无 115/ed2k/磁力时由 match_skip_cloud_share_title 直接跳过
        re.compile(r"迅雷(?:\s*(?:云盘|网盘|雲盤|網盤))?", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "pikpak",
        "PikPak网盘",
        RE_PIKPAK_SHARE,
        re.compile(r"pik\s*pak", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "baidu",
        "百度网盘",
        RE_BAIDU_SHARE,
        # 裸「百度」「度盘」也算；「百度+115eD2k」等并存由 title_has_target 挡住
        re.compile(r"百度(?:\s*(?:网盘|雲盤|云盘|網盤))?|百度云|度盘|度盤", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "quark",
        "夸克网盘",
        RE_QUARK_SHARE,
        re.compile(r"夸\s*克|quark", re.I),
        # True：标题常写 115eD2k/夸克，正文夸克推广链，真 ed2k 在「防失效备用版.txt」
        try_attachments=True,
    ),
    CloudShareSpec(
        "mega",
        "MEGA网盘",
        RE_MEGA_SHARE,
        # 勿裸匹配 mega：会误伤 meganmeow / Megan_myersss 等人名（tid=26632598/26710631）
        re.compile(
            r"(?<![A-Za-z0-9_])mega(?![A-Za-z0-9_])|mg\s*(?:网盘|網盤)",
            re.I,
        ),
        try_attachments=False,
    ),
    CloudShareSpec(
        "gdrive",
        "Google网盘",
        RE_GDRIVE_SHARE,
        re.compile(r"google|谷歌\s*(?:网盘|雲盤|云盘|網盤)", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "aliyun",
        "阿里云盘",
        RE_ALIYUN_SHARE,
        re.compile(r"阿里\s*(?:云盘|雲盤|网盘|網盤)|aliyun|alipan", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "tianyi",
        "天翼云盘",
        RE_TIANYI_SHARE,
        re.compile(r"天翼\s*(?:云盘|雲盤|网盘|網盤)|189\s*(?:云盘|雲盤)", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "pan123",
        "123云盘",
        RE_PAN123_SHARE,
        re.compile(r"123\s*(?:云盘|雲盤|网盘|網盤)|123pan", re.I),
        try_attachments=True,
    ),
    CloudShareSpec(
        "lanzou",
        "蓝奏云",
        RE_LANZOU_SHARE,
        re.compile(r"蓝奏\s*云|藍奏\s*雲|lanzou", re.I),
        # True：正文常夹带蓝奏「客户端/工具」推广链，真正 115eD2k 在附件 txt；
        # 与百度/迅雷一致，有附件区时先下附件再决定，避免把 115 帖误标成蓝奏跳过。
        try_attachments=True,
    ),
    CloudShareSpec(
        "uc",
        "UC网盘",
        RE_UC_SHARE,
        re.compile(r"UC\s*(?:网盘|網盤|云盘|雲盤)", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "weiyun",
        "微云",
        RE_WEIYUN_SHARE,
        re.compile(r"微\s*云|微\s*雲|weiyun", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "ctfile",
        "城通网盘",
        RE_CTFILE_SHARE,
        re.compile(r"城通\s*(?:网盘|網盤)|ctfile", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "onedrive",
        "OneDrive",
        RE_ONEDRIVE_SHARE,
        re.compile(r"onedrive|one\s*drive", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "dropbox",
        "Dropbox",
        RE_DROPBOX_SHARE,
        re.compile(r"dropbox", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "mediafire",
        "MediaFire",
        RE_MEDIAFIRE_SHARE,
        re.compile(r"media\s*fire", re.I),
        try_attachments=False,
    ),
    CloudShareSpec(
        "terabox",
        "Terabox",
        RE_TERABOX_SHARE,
        re.compile(r"tera\s*box", re.I),
        try_attachments=False,
    ),
)


def title_has_target_or_115_hint(title: str) -> bool:
    """标题是否含 115 / ed2k / 磁力等目标资源暗示（与网盘并存时勿判网盘）。"""
    t = (title or "").strip()
    return bool(t and _TITLE_HAS_TARGET_HINT_RE.search(t))


def _cloud_specs_in_title(title: str) -> list[CloudShareSpec]:
    t = (title or "").strip()
    if not t:
        return []
    return [
        spec
        for spec in SKIP_CLOUD_SHARE_SPECS
        if spec.title_re is not None and spec.title_re.search(t)
    ]


def _cloud_specs_in_resource_links(text: str) -> list[CloudShareSpec]:
    """只认网盘分享 URL（资源链），不认正文里的网盘关键字。"""
    blob = text or ""
    if not blob:
        return []
    hits: list[CloudShareSpec] = []
    seen: set[str] = set()
    for spec in SKIP_CLOUD_SHARE_SPECS:
        if spec.key in seen:
            continue
        if spec.url_re.search(blob):
            hits.append(spec)
            seen.add(spec.key)
    return hits


def _resource_has_target_or_115(text: str) -> bool:
    """资源链语料是否含 ed2k / 磁力 / 115 分享页 / 115sha。"""
    blob = text or ""
    if not blob:
        return False
    if ED2K_RE.search(blob) or MAGNET_RE.search(blob):
        return True
    if RE_115_SHARE.search(blob) or has_115_sha_link(blob):
        return True
    return False


def match_skip_cloud_share_link(text: str) -> CloudShareSpec | None:
    """资源链「仅一种跳过网盘 URL、且无 ed2k/磁力/115」→ 可跳过。

    115 与百度等同时出现、或多种网盘并存 → 不判网盘跳过。
    不再用「正文里出现任意一条网盘链」硬跳。
    """
    blob = text or ""
    if not blob or _resource_has_target_or_115(blob):
        return None
    hits = _cloud_specs_in_resource_links(blob)
    if len(hits) == 1:
        return hits[0]
    return None


def match_skip_cloud_share_title(title: str) -> CloudShareSpec | None:
    """标题「只点名一种网盘、且无 115/ed2k/magnet/磁力」→ 可跳过。

    裸写【迅雷】【百度】【度盘】【夸克】也算对应网盘；
    与 ed2k / 115 / magnet / 磁力 等同时出现 → 不判。
    【百度网盘+115eD2k】/【百度+夸克】这类并存 → 不判。
    """
    t = (title or "").strip()
    if not t or title_has_target_or_115_hint(t):
        return None
    hits = _cloud_specs_in_title(t)
    if len(hits) == 1:
        return hits[0]
    return None

SOFT_AD_TITLE_HINTS = ("名人名言", "佛教谚语", "请稍候", "Just a moment")
GENERIC_TITLES = frozenset({"提示信息", "提示", "手机版", "请稍候", "佛教谚语"})
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


def post_text(html: str, *, all_floors: bool = False) -> str:
    """帖内正文纯文本。默认取楼主各层（+附件注入块），忽略路人回帖。

    all_floors=True 时拼接全部 postmessage_*（含回帖；仅诊断/兼容用）。
    """
    if not all_floors:
        try:
            from parsers.content import extract_link_corpus_html

            corpus = extract_link_corpus_html(html or "")
            if corpus:
                text = corpus
                try:
                    from parsers.content import restore_cloudflare_emails

                    text = restore_cloudflare_emails(text)
                except Exception:
                    pass
                text = re.sub(r"<[^>]+>", "\n", text)
                return re.sub(r"\s+", " ", text).strip()
        except Exception:
            pass
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


def _lz_gate_blob(html: str) -> str:
    """需回复/购买等门控语料：楼主帖块（含 locked），无则退回整页。"""
    try:
        from parsers.content import extract_lz_scope_html

        scope = extract_lz_scope_html(html or "")
        if scope:
            return scope
    except Exception:
        pass
    return html or ""


_SELL_CONTENT_RE = re.compile(
    r"""<(?:div|section|td|span)[^>]*class=["'][^"']*\bsell_content\b[^"']*["'][^>]*>(.*?)</(?:div|section|td|span)>""",
    re.I | re.S,
)
_BUYTOPIC_NEIGHBOR_RE = re.compile(
    r""".{0,240}(?:action=buytopic|buytopicUrl).{0,360}""",
    re.I | re.S,
)


def _purchase_gate_blob(html: str) -> str:
    """购买门语料：楼主帖 + PHPWind sell_content / buytopic 邻域。

    2048 常把「本内容需向作者支付 + 0金币」放在 #read_tpc 外的 .sell_content，
    仅扫楼主正文会漏判 0 元贴。
    """
    raw = html or ""
    parts = [_lz_gate_blob(raw), post_text(raw)]
    for m in _SELL_CONTENT_RE.finditer(raw):
        parts.append(m.group(0))
    if "buytopic" in raw.lower() or "需向作者支付" in raw:
        for m in _BUYTOPIC_NEIGHBOR_RE.finditer(raw):
            parts.append(m.group(0))
            if len(parts) > 8:
                break
    return "\n".join(p for p in parts if p)


def has_thread_post_body(html: str) -> bool:
    h = html or ""
    return bool(POSTMESSAGE_RE.search(h) or PHPWIND_BODY_RE.search(h))


def is_mobile_thread_shell(html: str) -> bool:
    """识别手机版空壳帖页（无正文）。"""
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
    if len(html) < 12000 and ("viewthread" in lowered or "thread-" in lowered or "read.php" in lowered):
        return "forumdisplay" not in lowered and "thread.php" not in lowered
    return False

def has_target_link(text: str, link_kind: str) -> bool:
    """板块目标链：磁力板 / 电驴板均同时认 magnet 与 ed2k（转帖区常混发）。

    各板均认 115 网盘分享页（分享码资源可入库）。
    """
    raw = text or ""
    # 快路径：标准链无需全篇 normalize（爬虫判帖热路径）
    if ED2K_RE.search(raw) or MAGNET_RE.search(raw) or RE_115_SHARE.search(raw):
        return True
    from parsers.ed2k import normalize_ed2k_corpus
    from parsers.magnet import normalize_magnet_corpus

    blob = normalize_ed2k_corpus(normalize_magnet_corpus(raw))
    return bool(
        ED2K_RE.search(blob) or MAGNET_RE.search(blob) or RE_115_SHARE.search(blob)
    )


def has_115_sha_link(text: str) -> bool:
    """识别 115sha 直链：115://文件名|size|hash|hash。

    附件语料常把长链拆成多行，匹配前去掉空白再搜。
    """
    if not text or "|" not in text:
        return False
    if RE_115_SHA.search(text):
        return True
    # 仅当存在换行空白拆链时才压空白再搜，避免整篇大语料无谓 compact
    if "\n" not in text and "\r" not in text:
        return False
    compact = re.sub(r"\s+", "", text)
    return compact != text and bool(RE_115_SHA.search(compact))


def should_skip_as_115sha_only(text: str) -> bool:
    """语料含 115sha（115:// 或裸 sha1 管线），且无 magnet/ed2k/115分享 时才整帖跳过。

    与标题/文件名「115ed2k」无关——那是电驴链标，不能凭文件名推断为 115sha。
    同一压缩包内常同时有 Excel 磁力与 sha1.txt；有磁力则不应因 115sha 丢弃。
    """
    raw = text or ""
    if not raw:
        return False
    # 先快路径：已有可入库链则不必跑 115sha 正则（大合集附件上可达数十秒）
    low = raw.lower()
    if "magnet:" in low or "ed2k://" in low:
        return False
    if has_115_share_link(raw):
        return False
    return has_115_sha_link(raw)


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


def has_quark_share_link(text: str) -> bool:
    """识别夸克网盘分享：pan.quark.cn/s/..."""
    return bool(RE_QUARK_SHARE.search(text or ""))


def has_mega_share_link(text: str) -> bool:
    """识别 MEGA 分享：mega.nz/file|folder|…"""
    return bool(RE_MEGA_SHARE.search(text or ""))


def has_gdrive_share_link(text: str) -> bool:
    """识别 Google Drive：drive.google.com / docs.google.com。"""
    return bool(RE_GDRIVE_SHARE.search(text or ""))


def has_aliyun_share_link(text: str) -> bool:
    return bool(RE_ALIYUN_SHARE.search(text or ""))


def has_tianyi_share_link(text: str) -> bool:
    return bool(RE_TIANYI_SHARE.search(text or ""))


def has_pan123_share_link(text: str) -> bool:
    return bool(RE_PAN123_SHARE.search(text or ""))


def has_lanzou_share_link(text: str) -> bool:
    return bool(RE_LANZOU_SHARE.search(text or ""))


def has_uc_share_link(text: str) -> bool:
    return bool(RE_UC_SHARE.search(text or ""))


def has_weiyun_share_link(text: str) -> bool:
    return bool(RE_WEIYUN_SHARE.search(text or ""))


def has_ctfile_share_link(text: str) -> bool:
    return bool(RE_CTFILE_SHARE.search(text or ""))


def has_onedrive_share_link(text: str) -> bool:
    return bool(RE_ONEDRIVE_SHARE.search(text or ""))


def has_dropbox_share_link(text: str) -> bool:
    return bool(RE_DROPBOX_SHARE.search(text or ""))


def has_mediafire_share_link(text: str) -> bool:
    return bool(RE_MEDIAFIRE_SHARE.search(text or ""))


def has_terabox_share_link(text: str) -> bool:
    return bool(RE_TERABOX_SHARE.search(text or ""))


def title_is_xunlei_cloud_without_ed2k_magnet(title: str) -> bool:
    """标题标明迅雷云盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "xunlei"


def title_is_pikpak_without_ed2k_magnet(title: str) -> bool:
    """标题标明 PikPak，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "pikpak"


def title_is_baidu_pan_without_ed2k_magnet(title: str) -> bool:
    """标题标明百度网盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "baidu"


def title_is_quark_without_ed2k_magnet(title: str) -> bool:
    """标题标明夸克网盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "quark"


def title_is_mega_without_ed2k_magnet(title: str) -> bool:
    """标题标明 MEGA / mg网盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "mega"


def title_is_gdrive_without_ed2k_magnet(title: str) -> bool:
    """标题标明 Google 网盘，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。"""
    spec = match_skip_cloud_share_title(title)
    return spec is not None and spec.key == "gdrive"

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


def title_has_115ed2k_hint(title: str) -> bool:
    """标题是否标明 115ed2k / 115eD2k（指电驴链，与 115sha / 115:// 无关）。"""
    lower = re.sub(r"\s+", "", (title or "").lower())
    return "115ed2k" in lower


def title_is_115sha_without_ed2k_magnet(title: str) -> bool:
    """标题标明 115sha / 【sha1】，且未写 ed2k / magnet / 磁力 / 电驴 → 直接跳过。

    与【115ed2k】无关：后者是电驴资源标，即使带「115」也不得按 115sha 跳过。
    """
    t = (title or "").strip()
    if not t:
        return False
    # 115ed2k ≠ 115sha（两种链）；标题含 115ed2k 一律不当 115sha 帖
    if title_has_115ed2k_hint(t):
        return False
    lower = re.sub(r"\s+", "", t.lower())
    has_sha = (
        "115sha" in lower
        or bool(re.search(r"\[?\s*115\s*sha", t, re.I))
        or bool(re.search(r"[【\[]\s*sha1\s*[】\]]", t, re.I))
    )
    if not has_sha:
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


_LIST_TRUNC_END_RE = re.compile(r"(?:\.{3}|…)\s*$")
_LIST_TRUNC_BEFORE_CAP_RE = re.compile(r"(?:\.{3}|…)【")

# 末尾未闭合容量段：【8V/2配额 → 自动补】
_OPEN_CAPACITY_TAIL_RE = re.compile(r"[【［\[]([^【［\[】］\]]*)$")
_CAPACITY_TAIL_COMPLETE_RE = re.compile(
    r"(?:"
    r"配额|配額"
    r"|\d+(?:\.\d+)?\s*(?:[Vv]|[ＧGｇg][ＢBｂb]?|[ＰPｐp])"
    r")\s*$",
    re.I,
)


def close_trailing_capacity_bracket(title: str) -> str:
    """标题末尾容量/配额括号未闭合时补后括号。

    例：``…【5V/2.49GB/5配额`` → ``…【5V/2.49GB/5配额】``
    非容量未闭合（如 ``【苗条细腰``）不动。
    """
    t = (title or "").rstrip()
    if not t:
        return title or ""
    if t[-1:] in "】］]":
        return t
    m = _OPEN_CAPACITY_TAIL_RE.search(t)
    if not m:
        return t
    inner = (m.group(1) or "").strip()
    if not inner or not _CAPACITY_TAIL_COMPLETE_RE.search(inner):
        return t
    # 与开括号配对的闭括号
    opener = t[m.start()]
    closer = {"【": "】", "［": "］", "[": "]"}.get(opener, "】")
    return t + closer


def title_looks_list_truncated(title: str) -> bool:
    """列表页/异常截断标题：末尾 … / ...【容量 被砍 / 未闭合括号收尾。

    文案中间的「爱上…私下」不算截断（后面还有完整句子）。
    """
    t = close_trailing_capacity_bracket(title or "").strip()
    if not t:
        return False
    if _LIST_TRUNC_END_RE.search(t):
        return True
    if _LIST_TRUNC_BEFORE_CAP_RE.search(t):
        return True
    if t[-1:] in "【［[（(":
        return True
    return False


def coalesce_thread_title(*candidates: str) -> str:
    """帖标题以列表扫描为准：调用方须把 list_title 放第一位。

    列表可识别则直接用（补未闭合容量括号、剥「影片名称」标签）；
    仅当列表空/伪标题时，才用后续帖页候选兜底。
    不再用帖内更长 subject/正文覆盖列表，避免污染。
    """
    from parsers.resource_names import unwrap_subject_film_title

    for c in candidates:
        t = (c or "").strip()
        if not t or not title_recognizable(t):
            continue
        return close_trailing_capacity_bracket(unwrap_subject_film_title(t))
    return ""


def prefer_fuller_title(subject: str, body_name: str) -> str:
    """兼容旧调用：帖标题不再用正文补全，始终保留 subject。"""
    s = (subject or "").strip()
    return s if s else (body_name or "").strip()


def is_safe_or_soft_shell(html: str) -> bool:
    """站点软文 / R18 安全壳 / CF 中间页。

    真帖（有一楼正文）即使较短、页脚未抓全，也不得当成软文壳。
    含 tid=1742422 类：楼内 attach 嵌套整页广告 HTML（带 static/safe/），勿整帖当壳。
    """
    if not html:
        return True
    title = page_title(html)
    if any(h in title for h in SOFT_AD_TITLE_HINTS):
        return True
    # 真帖一楼优先：正文里夹带的转义软文片段不算壳
    if has_thread_post_body(html):
        return False
    # 安全壳脚本（名人名言 / R18 门）—— 仅无正文时生效
    if "var safeid" in html or "static/safe/" in html.lower():
        return True
    # 无论坛页脚的短页：仅当也无一楼正文时才视为中间页
    # （旧逻辑只要 <5KB 且无 Powered by 就判软文，会误伤「需回复」等真帖片段）
    lowered = html.lower()
    has_engine_footer = (
        "Powered by Discuz" in html
        or "powered by phpwind" in lowered
        or "powered by phpwind" in lowered.replace("&nbsp;", " ")
        or "id=\"read_tpc\"" in lowered
        or "id='read_tpc'" in lowered
    )
    if not has_engine_footer and len(html) < 5000:
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
    return not has_thread_post_body(html)


def is_missing_thread(html: str, title: str = "") -> bool:
    """识别「没有找到帖子 / 主题不存在」等空洞页。

    只认明确文案。PHPWind 空「提示信息」（限流/临时错误）不得当成永久不存在。
    """
    if not html and not title:
        return False
    tit = (title or page_title(html) or "").strip()
    blob = f"{tit}\n{html or ''}"
    return any(m in blob for m in MISSING_THREAD_MARKERS)


def is_empty_tip_page(html: str) -> bool:
    """空提示页：标题为提示信息/通用壳，无一楼正文，也无明确删帖/权限文案。

    常见于 PHPWind 限流、线路抖动；应重试而非永久跳过。
    """
    if not html or has_thread_post_body(html):
        return False
    tit = normalize_title_core(page_title(html))
    if not (
        tit == "提示信息"
        or tit in GENERIC_TITLES
        or (page_title(html) or "").strip().startswith("提示信息")
    ):
        return False
    blob = html or ""
    if any(m in blob for m in MISSING_THREAD_MARKERS):
        return False
    if any(m in blob for m in ACCESS_DENIED_MARKERS):
        return False
    if any(m in blob for m in LOGIN_MARKERS):
        return False
    return True


def is_thread_moderator_blocked(html: str) -> bool:
    """管理员/版主屏蔽：正文 locked，永久不可抓。只认楼主帖块。"""
    if not html:
        return False
    blob = _lz_gate_blob(html)
    if any(m in blob for m in MODERATOR_BLOCKED_MARKERS):
        return True
    body = re.sub(r"<[^>]+>", "\n", blob)
    return any(m in body for m in MODERATOR_BLOCKED_MARKERS)


def is_thread_author_banned(html: str) -> bool:
    """作者被禁止或删除，内容自动屏蔽。

    必须明确出现「作者被禁止」；若一楼已有有效正文/链接，视为正常帖（避免误跳过）。
    优先楼主帖块；scope 偶发抽到侧栏漏 locked 时回退全页（再用正文长度兜底）。
    """
    if not html:
        return False
    blob = _lz_gate_blob(html)
    plain = re.sub(r"<[^>]+>", "\n", blob)
    # locked 内常包 <em>…</em>，勿用 [^<]*
    locked_re = re.compile(
        r'class=["\']locked["\'][^>]*>.{0,160}?作者被禁止',
        re.I | re.S,
    )
    locked_hit = bool(locked_re.search(blob))
    text_hit = any(m in blob or m in plain for m in AUTHOR_BANNED_MARKERS)
    if not (locked_hit or text_hit):
        locked_hit = bool(locked_re.search(html))
        text_hit = any(m in html for m in AUTHOR_BANNED_MARKERS)
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
    只认楼主帖块，忽略回帖里的引用/复读。
    """
    if not html:
        return False
    blob = _lz_gate_blob(html)
    if any(m in blob for m in REPLY_MARKERS):
        return True
    if _REPLY_GATE_RE.search(blob):
        return True
    # 去标签后：请<a>回复</a> → 「请 回复」，再压掉空白便于匹配
    plain = re.sub(r"<[^>]+>", " ", blob)
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
    if "showhide" in blob.lower() and (
        "请回复" in plain_compact or "回复后才能" in plain_compact
    ):
        return True
    return False


def extract_purchase_price(html: str) -> int | None:
    """从购买门控文案解析售价；无门控或不含数字时返回 None。"""
    if not html:
        return None
    blob = _purchase_gate_blob(html)
    plain = re.sub(r"<[^>]+>", " ", blob)
    plain = re.sub(r"\s+", " ", plain)
    if not any(m in plain for m in PURCHASE_MARKERS):
        # 去标签后仍可能被拆开；再扫原始 blob
        if not any(m in blob for m in PURCHASE_MARKERS):
            return None
    m = _PURCHASE_PRICE_RE.search(plain) or _PURCHASE_PRICE_RE.search(blob)
    if not m:
        return None
    for g in m.groups():
        if g is not None and str(g).isdigit():
            return int(g)
    return None


_PURCHASE_BUY_LOOSE_RE = re.compile(
    r"""(?:job\.php\?[^\"'\s<>]*action=buytopic[^\"'\s<>]*|action=buytopic[^\"'\s<>]*)""",
    re.I,
)


def extract_purchase_buy_url(html: str, base_url: str = "") -> str:
    """提取免费/付费购买按钮链接（PHPWind buytopic / Discuz pay）。"""
    if not html:
        return ""
    from urllib.parse import urljoin

    m = _PURCHASE_BUY_HREF_RE.search(html)
    href = ""
    if m:
        href = (m.group(1) or "").replace("&amp;", "&").strip()
    if not href:
        # 部分模板把购买链放在 JS / hidden input，无 a[href]
        m2 = _PURCHASE_BUY_LOOSE_RE.search(html)
        if m2:
            href = (m2.group(0) or "").replace("&amp;", "&").strip()
            if not href.lower().startswith("job.php") and "job.php" not in href.lower():
                if href.lower().startswith("action="):
                    href = "job.php?" + href
    if not href:
        return ""
    if base_url:
        return urljoin(base_url, href)
    return href


def purchase_gate_kind(html: str) -> str:
    """购买门控分类：none | free | paid。

    - free：售价 0，可尝试点购买后入库
    - paid：售价>0 或无法解析价格的购买门 → 普通爬跳过，留给账号爬
    """
    if not html:
        return "none"
    # 大页快拒：无购买文案则不做楼主抽取 / 去标签（合集帖主路径）
    if not any(m in html for m in PURCHASE_MARKERS):
        return "none"
    if is_reply_required_post(html):
        return "none"
    blob = _purchase_gate_blob(html)
    plain = re.sub(r"<[^>]+>", " ", blob)
    plain = re.sub(r"\s+", " ", plain)
    if not any(m in blob or m in plain for m in PURCHASE_MARKERS):
        return "none"
    price = extract_purchase_price(html)
    if price == 0:
        return "free"
    return "paid"


def is_purchase_required_post(html: str) -> bool:
    """是否付费购买门（售价>0 或有门控但解析不出 0）。

    0 元购买不算「需购买拦截」——调用方应先尝试解锁再解析入库。
    """
    return purchase_gate_kind(html) == "paid"


def is_free_purchase_post(html: str) -> bool:
    return purchase_gate_kind(html) == "free"


def is_non_target_cloud_share(*, link_kind: str, text: str) -> bool:
    """ED2K 板：资源链只有跳过类网盘 URL（可多种）、无电驴/磁力/115。"""
    if link_kind != "ed2k":
        return False
    from parsers.ed2k import normalize_ed2k_corpus
    from parsers.magnet import normalize_magnet_corpus

    blob = normalize_ed2k_corpus(normalize_magnet_corpus(text or ""))
    if _resource_has_target_or_115(blob):
        return False
    return bool(_cloud_specs_in_resource_links(blob))


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
        return any(
            x in t
            for x in (
                "magnet",
                "磁力",
                "磁链",
                "种子",
                "torrent",
                "bt",
                "ed2k",
                "115",
                "98t",
                "电驴",
            )
        )
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
    """是否有可解析的资源附件（txt/zip/rar/torrent）。预览图不算。

    大页热路径：无附件线索则跳过 BeautifulSoup；同页指纹结果缓存，
    避免 judge 内十余次重复抽附件。
    """
    if not html:
        return False
    fp = _attach_zone_fp(html)
    cached = _ATTACH_ZONE_FP_MEMO.get(fp)
    if cached is not None:
        return cached
    if not _ATTACH_ZONE_HINT_RE.search(html):
        ok = False
    else:
        from parsers.attachments import extract_download_attachments

        ok = bool(extract_download_attachments("", html))
    _ATTACH_ZONE_FP_MEMO[fp] = ok
    if len(_ATTACH_ZONE_FP_MEMO) > 128:
        _ATTACH_ZONE_FP_MEMO.clear()
        _ATTACH_ZONE_FP_MEMO[fp] = ok
    return ok
