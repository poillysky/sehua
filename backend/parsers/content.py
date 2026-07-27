"""Structured fields and plain text from Discuz thread HTML."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from parsers.resource_names import (
    FILM_TITLE_FORMS,
    FORMAT_FIELD_FORMS,
    NOTE_FIELD_FORMS,
    RESOURCE_TITLE_FORMS,
    SIZE_FIELD_FORMS,
    STRUCTURE_FIELD_BOUNDARY_FORMS,
    STRUCTURE_FIELD_CLOSE,
    STRUCTURE_FIELD_OPEN,
    SUBRESOURCE_TITLE_LABELS,
    SUBRESOURCE_TITLE_MATCH_FORMS,
    TORRENT_FIELD_FORMS,
    _ANY_STRUCTURE_BRACKET_LABEL_RE,
    _LABELED_STRUCTURE_FIELD_RE,
    collapse_structure_label_gaps,
    detect_structure_bracket_pair,
    normalize_structure_label_key,
    structure_labels_alt,
)

# BT + ED2K board label styles commonly used on sehuatang / 2048（抽样核对）
LABEL_KEYS = tuple(STRUCTURE_FIELD_BOUNDARY_FORMS)

# 详情描述按板块白名单（与论坛配置「结构卡片」字段对齐）
# 不含：预览类、种子期限、下载工具、资源链接区等

_BT_FIDS = frozenset(
    {"2", "36", "37", "103", "107", "160", "104", "38", "151", "152", "39"}
)

# 默认（未知板）：综合区口径
DISPLAY_DESCRIPTION_LABELS = (
    "资源名称",
    "资源类型",
    "资源大小",
    "是否有码",
    "有无第三方水印",
    "解压密码",
)

DESCRIPTION_LABEL_ALIASES = {
    "影片名称": "资源名称",
    "影片名稱": "资源名称",
    "資源名稱": "资源名称",
    "资源名稱": "资源名称",
    "資源名称": "资源名称",
    "影片名": "资源名称",
    "资源名": "资源名称",
    "資源名": "资源名称",
    "视频名称": "资源名称",
    "視頻名稱": "资源名称",
    "作品名称": "资源名称",
    "作品名稱": "资源名称",
    "片名": "资源名称",
    "影片标题": "资源名称",
    "影片標題": "资源名称",
    "资源标题": "资源名称",
    "資源標題": "资源名称",
    "影片格式": "资源类型",
    "資源類型": "资源类型",
    "资源類型": "资源类型",
    "資源类型": "资源类型",
    "檔案格式": "资源类型",
    "文件格式": "资源类型",
    "文件大小": "资源大小",
    "檔案大小": "资源大小",
    "档案大小": "资源大小",
    "影片容量": "资源大小",
    "影片大小": "资源大小",
    "資源大小": "资源大小",
    "有无码": "是否有码",
    "有無碼": "是否有码",
    "是否有碼": "是否有码",
    "影片码别": "是否有码",
    "影片碼別": "是否有码",
    "有无水印": "有无第三方水印",
    "有無浮水印": "有无第三方水印",
    "第三方水印": "有无第三方水印",
    "第三方浮水印": "有无第三方水印",
    "有無第三方浮水印": "有无第三方水印",
    "提取密码": "解压密码",
    "提取密碼": "解压密码",
    "解壓密碼": "解压密码",
    "解压码": "解压密码",
    "解壓碼": "解压密码",
    "提取码": "解压密码",
    "提取碼": "解压密码",
    "资源密码": "解压密码",
    "資源密碼": "解压密码",
    "资源码": "解压密码",
    "資源碼": "解压密码",
}

# profile: labels 顺序；exclusive 组内只保留靠前且有值的一项；aliases 写入展示键
BOARD_DESCRIPTION_PROFILES: dict[str, dict] = {
    "bt": {
        "labels": (
            "影片名称",
            "出演女优",
            "影片容量",
            "影片大小",
            "是否有码",
            "影片格式",
            "影片码别",
            "解压密码",
        ),
        "exclusive": (("影片容量", "影片大小"),),
        "aliases": {
            "资源名称": "影片名称",
            "資源名稱": "影片名称",
            "影片名稱": "影片名称",
            "有无码": "是否有码",
            "文件大小": "影片大小",
            "资源大小": "影片大小",
            "提取密码": "解压密码",
            "资源密码": "解压密码",
        },
        "title_as": "影片名称",
    },
    "95": {
        "labels": (
            "资源名称",
            "资源类型",
            "资源大小",
            "是否有码",
            "有无第三方水印",
            "解压密码",
        ),
        "exclusive": (),
        "aliases": DESCRIPTION_LABEL_ALIASES,
        "title_as": "资源名称",
    },
    "141": {
        "labels": (
            "资源名称",
            "资源类型",
            "资源数量",
            "资源大小",
            "有无水印",
            "是否有码",
            "解压密码",
        ),
        "exclusive": (),
        "aliases": {
            "影片名称": "资源名称",
            "影片名稱": "资源名称",
            "資源名稱": "资源名称",
            "文件大小": "资源大小",
            "影片容量": "资源大小",
            "影片大小": "资源大小",
            "有无第三方水印": "有无水印",
            "有无码": "是否有码",
            "提取密码": "解压密码",
            "资源密码": "解压密码",
        },
        "title_as": "资源名称",
    },
    "142": {
        "labels": (
            "资源名称",
            "影片名称",
            "文件大小",
            "影片大小",
            "是否有码",
            "解压密码",
        ),
        "exclusive": (("资源名称", "影片名称"), ("文件大小", "影片大小")),
        "aliases": {
            "资源大小": "文件大小",
            "影片容量": "影片大小",
            "影片名稱": "影片名称",
            "資源名稱": "资源名称",
            "有无码": "是否有码",
            "提取密码": "解压密码",
            "资源密码": "解压密码",
        },
        "title_as": "资源名称",
    },
}

# 2048 PHPWind：展示描述不含裸 hash（已转磁力）；字段与 STRUCTURE_LABELS_2048 / 结构卡片对齐
# 抽样（各白名单板随机帖）后补全：影片标题→片名、檔案大小、繁简异写归一
_PW_2048_BT_ALIASES: dict[str, str] = {
    "影片名稱": "影片名称",
    "影片标题": "影片名称",
    "影片標題": "影片名称",
    "影片题名": "影片名称",
    "影片題名": "影片名称",
    "資源名稱": "资源名称",
    "资源名": "资源名称",
    "影片格式": "影片格式",
    "資源類型": "资源类型",
    "资源類型": "资源类型",
    "文件大小": "影片大小",
    "檔案大小": "影片大小",
    "档案大小": "影片大小",
    "资源大小": "影片大小",
    "資源大小": "影片大小",
    "影片容量": "影片大小",
    "是否有碼": "是否有码",
    "有无码": "是否有码",
    "有無碼": "是否有码",
    "影片時間": "影片时间",
    "影片時長": "影片时长",
    "发布时间": "发布时间",
    "發布時間": "发布时间",
    "解析度": "分辨率",
    "有無浮水印": "有无水印",
    "有无第三方水印": "有无水印",
    "有無第三方水印": "有无水印",
    "有無第三方浮水印": "有无水印",
    "下载方式": "下载方式",
    "下載方式": "下载方式",
    "作種期限": "作种期限",
    "种子期限": "作种期限",
    "種子期限": "作种期限",
    "圖片預覽": "图片预览",
    "影片預覽": "影片预览",
    "影片截圖": "影片截图",
    "影片說明": "影片说明",
    "解壓密碼": "解压密码",
}

_PW_2048_BT_LABELS = (
    "影片名称",
    "中文片名",
    "影片格式",
    "是否有码",
    "影片时间",
    "影片时长",
    "影片大小",
    "发布时间",
    "分辨率",
    "作种期限",
    "有无水印",
    "资源名称",
    "资源类型",
    "资源数量",
    "下载方式",
)

_PW_2048_FIDS = frozenset(
    {"3", "318", "4", "5", "13", "15", "16", "18", "343", "195", "67"}
)

for _fid in _PW_2048_FIDS:
    BOARD_DESCRIPTION_PROFILES[_fid] = {
        "labels": _PW_2048_BT_LABELS,
        "exclusive": (("影片时间", "影片时长"),),
        "aliases": _PW_2048_BT_ALIASES,
        "title_as": "影片名称",
    }


def description_profile_for_board(board_fid: str | int | None) -> dict:
    """按主板块 fid 选结构卡片；兼容子版 key「151:823」。"""
    raw = str(board_fid or "").strip()
    fid = raw.split(":", 1)[0].strip() if raw else ""
    if fid in BOARD_DESCRIPTION_PROFILES:
        return BOARD_DESCRIPTION_PROFILES[fid]
    if fid in _BT_FIDS:
        return BOARD_DESCRIPTION_PROFILES["bt"]
    return {
        "labels": DISPLAY_DESCRIPTION_LABELS,
        "exclusive": (),
        "aliases": DESCRIPTION_LABEL_ALIASES,
        "title_as": "资源名称",
    }

_LABEL_ALT = structure_labels_alt(LABEL_KEYS)
# 与 resource_names._STRUCTURE_SEP 对齐（标签→值分隔）
_STRUCTURE_SEP = r"[:：︰﹒．.｜|/／·・•‧＝=\-_;；,，〜～﹕→]?"
# 值截到下一个字段标签为止（同行/换行均可）。
# 匹配前须 collapse_structure_label_gaps，故标签用字面 alt。
LABEL_RE = re.compile(
    rf"{STRUCTURE_FIELD_OPEN}\s*({_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE}\s*{_STRUCTURE_SEP}\s*"
    rf"(.*?)(?="
    rf"(?:\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE})"  # 已知字段
    rf"|(?:{_ANY_STRUCTURE_BRACKET_LABEL_RE.pattern}\s*[:：︰﹒．.｜|/／·・•‧＝=])"  # 任意「开标签闭：」
    rf"|$"
    rf")",
    re.I | re.S,
)

# 非片名：遇任意开闭括号标签即截（不问标签文字）
_NEXT_FIELD_RE = _ANY_STRUCTURE_BRACKET_LABEL_RE
# 片名：已知结构字段 OR 任意「开…闭+分隔」（装饰【合集】无冒号则仍会切；无分隔保留）
_KNOWN_NEXT_FIELD_RE = re.compile(
    rf"(?:"
    rf"\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE}"
    rf"|{_LABELED_STRUCTURE_FIELD_RE.pattern}"
    rf")",
    re.I,
)
# 片名裁剪：简繁/异写均走「仅已知结构字段」边界，避免【午夜寻花】等装饰括号截断
_TITLE_FIELD_LABELS = frozenset(
    normalize_structure_label_key(x)
    for x in (*SUBRESOURCE_TITLE_MATCH_FORMS, *SUBRESOURCE_TITLE_LABELS)
)


def _is_title_field_label(label: str) -> bool:
    lab = normalize_structure_label_key(label or "")
    return bool(lab) and lab in _TITLE_FIELD_LABELS
_SIZE_FIELD_LABELS = frozenset(
    {
        "资源大小",
        "資源大小",
        "文件大小",
        "檔案大小",
        "档案大小",
        "影片大小",
        "影片容量",
    }
)
# 82V+173P/6.7G/1配额 · 70.6G/1169V//7配额 · 807 M / 1V
# 允许前缀全角冒号/点号（2048 实录「︰5.23GB」）
_SIZE_VALUE_RE = re.compile(
    r"^[︰:：.\s]*("
    r"(?:"
    r"\d+(?:\.\d+)?\s*[GMTK]B?"
    r"|\d+\s*[VvPp]"
    r"|\d+\s*配额"
    r"|配额"
    r"|[/\+×xX\-\s]"
    r")+"
    r")",
    re.I,
)
# 种子文件名脏值（2048 合集帖正文残片「]ent」）
_BOGUS_TORRENT_NAME_RE = re.compile(
    r"^(?:\]?ent|\.?torrent|\]+)$",
    re.I,
)
# 预览类字段若是下载页/购买提示/纯磁链导语，则丢弃（勿当结构字段入库）
_BOGUS_PREVIEW_META_RE = re.compile(
    r"(?:"
    r"rmdown\.com|购买本帖|立即购买|购买人名单|需向作者支付"
    r"|下载磁链|磁力链接\s*$|磁力連接"
    r")",
    re.I,
)
_HASH_META_LABEL_HINTS = (
    "特征",
    "特徵",
    "验证",
    "驗證",
    "试证",
    "試證",
    "种子特",
    "種子特",
    "哈希",
    "雜湊",
)
# Discuz 一楼正文起点（仅数字楼 id，跳过 postmessage_attach* 注入）
_OP_POST_START_RE = re.compile(r'id="postmessage_(\d+)"[^>]*>', re.I)
# 一楼正文结束：下一帖 / 评论区 / 表尾（切在开标签前，避免残留 `<div`）
_OP_POST_END_RE = re.compile(
    r'<[^>]+id="postmessage_|<[^>]+id="post_\d+|<[^>]+id="comment_|'
    r'<!--\s*end\s*post|</tbody>',
    re.I,
)
# 楼主标记：ico_lz.png 或 authi 里的「楼主」（勿用「只看该作者」，每层都有）
_LZ_MARK_RE = re.compile(
    r"ico_lz\.png|(?:^|>|&nbsp;)\s*楼主(?:\s|<|\||$)",
    re.I | re.M,
)

# 字段值里常见的附件区 / 楼层 / 页脚噪声（非密码字段也裁）
_FIELD_NOISE_RE = re.compile(
    r"(?:"
    r"下载附件|下载次数|点击文件名下载|阅读权限\s*:"
    r"|复制代码|收起\s*理由|查看全部评分"
    r"|发表于\s*\d{4}|只看该作者|使用道具|返回列表"
    r"|Powered by Discuz|快速回复|本版积分规则"
    r"|当前离线|当前在线"
    r"|回复\s*支持|回复\s*使用道具|本帖最后由"
    r"|ed2k://|magnet:\?"
    r"|第\s*\d+\s*页|下一页|上一页"
    r")",
    re.I,
)

# 枚举型短字段：取值到首个空白/标点为止，避免一楼边界失败时吞进回复
_SHORT_ENUM_LABELS = frozenset(
    {
        "资源类型",
        "是否有码",
        "有无码",
        "影片码别",
        "有无第三方水印",
        "有无水印",
        "第三方水印",
        "影片格式",
    }
)
_SHORT_ENUM_VALUE_RE = re.compile(r"^([^\s，,。；;|/]+)")
# 「解压密码是www.98T.la@」——「是/为」是系词不是密码；也兼容冒号/等号
# 另有【资源密码】写法（】与冒号之间可无空格）
# 帖内常见简写「解压码：」（无「密」字）；www.98T.la 与 @ 常被拆成链接+彩色字
PASSWORD_RE = re.compile(
    r"(?:解压|提取|资源)\s*密?\s*码\s*】?\s*(?:[:：=]|是|为)?\s*"
    r"((?:www\.)?98[Tt]\.la\s*@?|[^\s【】\n，,。；;]+)",
    re.I,
)
# 帖内常见：单独「密码/码」后跟 www.98T.la@（无解压/提取前缀，常夹在 font 标签里）
PASSWORD_BARE_98T_RE = re.compile(
    r"(?:密码|码)\s*(?:[:：=]|是|为)?\s*((?:www\.)?98[Tt]\.la\s*@?)",
    re.I,
)
_PASSWORD_META_KEYS = ("解压密码", "提取密码", "资源密码", "解压码", "提取码", "资源码")
_PASSWORD_LABELS = frozenset(_PASSWORD_META_KEYS)
# 优先 zoomfile / file（Discuz 高清）、data-original（PHPWind 懒加载），再 src
IMG_TAG_RE = re.compile(r"<img\b([^>]*)>", re.I)
IMG_ATTR_RE = re.compile(
    r"""(?:zoomfile|file|data-original|data-src|data-lazy(?:-src)?|data-url|src)\s*=\s*["']([^"']+)["']""",
    re.I,
)
IMAGE_SKIP_MARKERS = (
    "static/image/smiley",
    "static/image/common/",
    "static/image/filetype",
    "static/image/hrline",
    "static/image/icon",
    "static/image/",
    "avatar",
    "uc_server/avatar",
    "uc_server/data/avatar",
    "uc_server/images/",
    "noavatar",
    "logo",
    "/emoji",
    "smiley",
    # Discuz 用户组/勋章等站内装饰，不是帖子预览图
    "attachment/common/",
    "usergroup_icon",
    "groupicon",
    "common_56_",
    "/icon/",
    "favicon",
    "medal/",
    "ranklist",
    "online_member",
    "online_moderator",
    "ico_lz",
    "pn_post",
    "thread-prev",
    "thread-next",
    "print.png",
    "userinfo.gif",
    "fj_btn",
    "arw_r.gif",
    "hot_1.gif",
    # 二维码 / 加群码常见命名
    "qrcode",
    "qr_code",
    "/qr/",
    "weixinqr",
    "wxqr",
    "wx_qr",
    "qqqr",
    "%e4%ba%8c%e7%bb%b4%e7%a0%81",  # 二维码
    # PHPWind / 2048 站内 UI、懒加载占位
    "thumb-ing",
    "images/wind/",
    "images/face/",
    "images/close",
    "images/notice",
    "images/level/",
    "/file/zip.gif",
    "/file/rar.gif",
    "tip_bottom",
    "tip/small",
)

# img class / id：头像、在线图标、勋章等
_IMG_NOISE_CLASS_RE = re.compile(
    r"""\bclass\s*=\s*["'][^"']*\b(?:authicn|avtm|avatar|md_ctrl)\b""",
    re.I,
)
_IMG_NOISE_ID_RE = re.compile(
    r"""\bid\s*=\s*["'][^"']*(?:authicon|md_\d|favatar)""",
    re.I,
)
# alt/title 明示二维码 / 头像
_IMG_NOISE_LABEL_RE = re.compile(
    r"(?:二维码|二維碼|qr\s*code|qrcode|头像|頭像|avatar|勋章|勳章|用户组|用戶組)",
    re.I,
)
_IMG_WH_RE = re.compile(
    r"""\b(?:width|height)\s*=\s*["']?(\d{1,4})""",
    re.I,
)
# 签名档 / 头像栏整块去掉再抽图（避免签名里的广告图、二维码进预览）
_STRIP_PREVIEW_BLOCKS_RE = re.compile(
    r"(?is)<div[^>]*\bclass\s*=\s*[\"'][^\"']*\b(?:sign|avatar|favatar)\b[^\"']*[\"'][^>]*>.*?</div>",
)
BLOCKCODE_RE = re.compile(
    r'<(?:div|pre)[^>]*class="[^"]*blockcode[^"]*"[^>]*>(.*?)</(?:div|pre)>',
    re.I | re.S,
)
# Cloudflare Email Obfuscation：把 1998@www.98T.la 这类「像邮箱」的解压密码藏进 data-cfemail
_CFEMAIL_A_RE = re.compile(
    r"""<a\b[^>]*\bdata-cfemail=["']([0-9a-fA-F]+)["'][^>]*>.*?</a>""",
    re.I | re.S,
)
_CFEMAIL_HREF_RE = re.compile(
    r"""<a\b[^>]*href=["']/cdn-cgi/l/email-protection#([0-9a-fA-F]+)["'][^>]*>.*?</a>""",
    re.I | re.S,
)
_CFEMAIL_SPAN_RE = re.compile(
    r"""<(?:span|em)\b[^>]*\bdata-cfemail=["']([0-9a-fA-F]+)["'][^>]*>.*?</(?:span|em)>""",
    re.I | re.S,
)
_EMAIL_PROTECTED_RE = re.compile(
    r"\[\s*email\s*protected\s*\]|email\s*&#160;\s*protected",
    re.I,
)


@dataclass(slots=True)
class ThreadContent:
    tid: int
    title: str
    plain_text: str
    blockcode_text: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    preview_images: list[str] = field(default_factory=list)
    extract_password: str = ""


def decode_cf_email(encoded: str) -> str:
    """Decode Cloudflare data-cfemail / email-protection# hex payload."""
    enc = (encoded or "").strip()
    if len(enc) < 4 or len(enc) % 2:
        return ""
    try:
        key = int(enc[:2], 16)
        chars = [chr(int(enc[i : i + 2], 16) ^ key) for i in range(2, len(enc), 2)]
        # 与 CF 前端一致：经 latin1/percent 还原后再出 Unicode
        raw = "".join(chars)
        try:
            return raw.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            return raw
    except (ValueError, OverflowError):
        return ""


def restore_cloudflare_emails(html: str) -> str:
    """把 Cloudflare 邮箱保护节点还原为明文（解压密码常被误伤）。"""

    def _repl(match: re.Match[str]) -> str:
        return decode_cf_email(match.group(1)) or match.group(0)

    text = html or ""
    text = _CFEMAIL_A_RE.sub(_repl, text)
    text = _CFEMAIL_HREF_RE.sub(_repl, text)
    text = _CFEMAIL_SPAN_RE.sub(_repl, text)
    return text


def _clean_text(raw: str) -> str:
    text = restore_cloudflare_emails(raw or "")
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = _EMAIL_PROTECTED_RE.sub(" ", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_title(html: str) -> str:
    m = re.search(r'id="thread_subject"[^>]*>(.*?)</(?:a|span|div)>', html, re.I | re.S)
    if m:
        return _strip_forum_title_suffix(_clean_text(m.group(1)))
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if m:
        return _strip_forum_title_suffix(_clean_text(m.group(1)))
    return ""


def _strip_forum_title_suffix(title: str) -> str:
    """去掉页标题尾部的板块/站名（2048 常见「片名 | 最新合集 - 论坛名」）。"""
    t = (title or "").strip()
    if not t:
        return ""
    # 先去站名，再去板块：`<title>片名 | 最新合集 - 人人为我论坛</title>`
    for sep in (" - ", " – ", " — "):
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    for sep in (" | ", "｜"):
        if sep in t:
            t = t.split(sep, 1)[0].strip()
            break
    return t


def extract_tid(html: str, fallback: int = 0) -> int:
    m = re.search(r"tid[=:]?\s*['\"]?(\d+)", html, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"thread-(\d+)-1-\d+\.html", html, re.I)
    return int(m.group(1)) if m else fallback


def extract_first_postmessage_html(html: str) -> str:
    """只取一楼 postmessage 正文，避免把回复楼/页脚揉进元数据。"""
    src = html or ""
    # PHPWind：完整 #read_tpc（含 comment_ 后的售价/电驴）；勿先被 Discuz postmessage 截断
    pw = _phpwind_post_html(src)
    if pw:
        return pw
    for m in _OP_POST_START_RE.finditer(src):
        # 仅纯数字楼层 id（1、2…）；跳过异常 id
        if not m.group(1).isdigit():
            continue
        start = m.end()
        end_m = _OP_POST_END_RE.search(src, start)
        end = end_m.start() if end_m else len(src)
        body = src[start:end].strip()
        if body:
            return body
    return src


def _is_phpwind_thread_html(html: str) -> bool:
    src = html or ""
    return 'id="read_tpc"' in src or "id='read_tpc'" in src or 'class="tpc_content"' in src


def _phpwind_post_html(html: str) -> str:
    if not _is_phpwind_thread_html(html):
        return ""
    try:
        from crawler.parser_phpwind import extract_phpwind_post_html

        pw = extract_phpwind_post_html(html or "")
        if pw and pw is not html and len(pw) < len(html or ""):
            return pw
        return pw or ""
    except Exception:
        return ""


def extract_lz_posts_html(html: str, *, limit: int = 5) -> list[str]:
    """取带「楼主」标的各层 postmessage（一楼 + 楼主二楼补链等）。

    路人回帖不纳入。limit 限制最多纳入几层楼主帖。
    PHPWind：优先 #read_tpc（Discuz 式 postmessage 会被 comment_ 截断，漏掉售价后的 ed2k）。
    """
    src = html or ""
    if not src:
        return []

    pw = _phpwind_post_html(src)
    if pw:
        return [pw]

    starts = [m for m in _OP_POST_START_RE.finditer(src) if m.group(1).isdigit()]
    posts: list[tuple[str, bool]] = []
    for i, m in enumerate(starts):
        start = m.end()
        end_m = _OP_POST_END_RE.search(src, start)
        end = end_m.start() if end_m else len(src)
        body = src[start:end].strip()
        if not body:
            continue
        # 仅看「上一帖结束 → 本帖 postmessage」之间的 authi，避免上一楼楼主标泄漏
        head_from = starts[i - 1].start() if i > 0 else max(0, m.start() - 2200)
        head = src[head_from : m.start()]
        is_lz = bool(_LZ_MARK_RE.search(head))
        posts.append((body, is_lz))

    if not posts:
        return []

    lim = max(1, int(limit or 5))
    out = [body for body, is_lz in posts if is_lz][:lim]
    if out:
        return out
    # 无楼主标时退回物理一楼
    return [posts[0][0]]


def extract_lz_scope_html(html: str, *, limit: int = 5) -> str:
    """主贴帖块（含 postmessage 前的 locked/需回复提示），不含回帖。

    用于需回复/购买等门控：提示常在 postmessage 外的同楼 DOM。
    门控只看第一层楼主帖（通常即一楼），避免二楼正文干扰。
    PHPWind：用完整 #read_tpc（含 comment_ 后的售价/电驴块）。
    """
    src = html or ""
    if not src:
        return ""

    pw = _phpwind_post_html(src)
    if pw:
        return pw

    starts = [m for m in _OP_POST_START_RE.finditer(src) if m.group(1).isdigit()]
    scopes: list[tuple[str, bool]] = []
    for i, m in enumerate(starts):
        start = m.end()
        end_m = _OP_POST_END_RE.search(src, start)
        end = end_m.start() if end_m else len(src)
        head_from = starts[i - 1].start() if i > 0 else max(0, m.start() - 2200)
        head = src[head_from : m.start()]
        is_lz = bool(_LZ_MARK_RE.search(head))
        # 含同楼头部（locked）+ 正文，便于门控文案命中
        scopes.append((src[head_from:end].strip(), is_lz))

    if not scopes:
        return ""

    for body, is_lz in scopes:
        if is_lz:
            return body
    return scopes[0][0]


def extract_link_corpus_html(html: str, *, limit: int = 5) -> str:
    """链接/子资源语料：楼主各层（含二楼补链）+ 附件注入块。

    路人回帖默认不参与；仅当标题/楼主明示「求磁力」类、且楼主正文无链时，
    才补入含 magnet/ed2k 的回帖（避免讨论帖/网盘帖被回帖链误入库）。

    已注入附件且附件内含目标链时：链语料以附件为准（正文样例链不并入）。
    """
    lz_parts: list[str] = list(extract_lz_posts_html(html, limit=limit))
    if not lz_parts:
        # PHPWind：#read_tpc / .tpc_content（无 Discuz postmessage_*）
        pw = _phpwind_post_html(html or "")
        if pw:
            lz_parts.append(pw)
    attach_parts: list[str] = []
    for m in re.finditer(
        r'id=["\']postmessage_attach\d+["\'][^>]*>(.*?)</div>',
        html or "",
        re.I | re.S,
    ):
        body = (m.group(1) or "").strip()
        if body:
            attach_parts.append(body)

    def _has_target_link_blob(blob: str) -> bool:
        low = (blob or "").lower()
        return (
            "magnet:" in low
            or "ed2k://" in low
            or "/torrent/" in low
            or "rmdown.com" in low
        )

    # 附件已注入且含目标链 → 只认附件（正文常夹带预览样例链）
    if attach_parts and _has_target_link_blob("\n".join(attach_parts)):
        return "\n".join(attach_parts)

    parts: list[str] = list(lz_parts)
    parts.extend(attach_parts)

    joined = "\n".join(parts).lower()
    has_body_link = _has_target_link_blob(joined)
    ask_blob = "\n".join(
        [
            extract_title(html or "") or "",
            parts[0] if parts else "",
        ]
    )
    asks_for_link = bool(
        re.search(
            r"求磁力|求磁[链鏈]|求种子|求種子|求\s*ed2k|求电驴|有无磁[力链鏈]",
            ask_blob,
            re.I,
        )
    )
    if not has_body_link and asks_for_link:
        # 楼主无链：扫回帖补 magnet/ed2k（限量）
        src = html or ""
        starts = [m for m in _OP_POST_START_RE.finditer(src) if m.group(1).isdigit()]
        extra = 0
        for i, m in enumerate(starts):
            start = m.end()
            end_m = _OP_POST_END_RE.search(src, start)
            end = end_m.start() if end_m else len(src)
            body = src[start:end].strip()
            if not body:
                continue
            if not _has_target_link_blob(body):
                continue
            # 跳过已在 parts 中的楼主层
            if any(body[:80] == (p or "")[:80] for p in parts):
                continue
            parts.append(body)
            extra += 1
            if extra >= 3:
                break
    return "\n".join(parts)


def attachment_corpus_has_target_links(html: str) -> bool:
    """inject 后的附件块是否已含 magnet/ed2k 等目标链。"""
    chunks: list[str] = []
    for m in re.finditer(
        r'id=["\']postmessage_attach\d+["\'][^>]*>(.*?)</div>',
        html or "",
        re.I | re.S,
    ):
        body = (m.group(1) or "").strip()
        if body:
            chunks.append(body)
    if not chunks:
        return False
    low = "\n".join(chunks).lower()
    return (
        "magnet:" in low
        or "ed2k://" in low
        or "/torrent/" in low
        or "rmdown.com" in low
    )


def _clip_field_value(
    value: str,
    *,
    password: bool = False,
    short_enum: bool = False,
    label: str = "",
) -> str:
    """裁掉粘在后面的下一结构标签、附件区与楼层噪声。

    非片名：遇任意开闭括号标签即截（自动识别【】［］[] 等，不问标签文字）。
    片名：已知结构字段，或「开…闭+分隔」形态（保留无分隔的装饰【合集】）。
    """
    # 2048/转帖常见：变体选择符、全角冒号前缀
    val = (value or "").replace("\r", "\n")
    val = re.sub(r"[\ufe0e\ufe0f\u200d\u200b\u200c\u200d]", "", val)
    val = " ".join(val.split())
    val = val.lstrip(":：︰.").strip()
    if not val:
        return ""
    # 片名截断前折叠下一字段标签字间空，便于字面 _LABEL_ALT 命中
    if _is_title_field_label(label):
        val = collapse_structure_label_gaps(val)
    # 名称可含嵌套装饰【标签】；其它字段遇到任意开闭括号标签即截
    next_re = _KNOWN_NEXT_FIELD_RE if _is_title_field_label(label) else _NEXT_FIELD_RE
    m = next_re.search(val)
    if m:
        val = val[: m.start()].strip()
    noise = _FIELD_NOISE_RE.search(val)
    if noise:
        val = val[: noise.start()].strip()
    if password:
        # 附件名粘在密码后：MyBigDick@x.txt 18OnlyGirls.rar (42.29 KB,
        m_att = re.search(
            r"\s+\S+\.(?:rar|zip|7z|txt|docx?|xlsx?|xls|torrent)\b",
            val,
            re.I,
        )
        if m_att:
            val = val[: m_att.start()].strip()
        # 密码通常是单 token；后面若跟中文说明再硬切
        m2 = re.search(r"\s+[\u4e00-\u9fff]", val)
        if m2:
            val = val[: m2.start()].strip()
        if len(val) > 120:
            val = val[:120].strip()
    elif short_enum:
        m3 = _SHORT_ENUM_VALUE_RE.match(val)
        if m3:
            val = m3.group(1).strip()
        if len(val) > 32:
            val = val[:32].rstrip()
    elif label in _SIZE_FIELD_LABELS or label in SIZE_FIELD_FORMS:
        # 大小后常跟博主导语 / rmdown URL / 【验証码】hash，只留容量串
        m4 = _SIZE_VALUE_RE.match(val)
        if m4:
            val = m4.group(1).strip().strip("/+-\u00d7xX \t")
        # 仍残留下一结构字段或 hash 时截掉（开括号不限【）
        m_next = re.search(
            rf"\s*(?:{STRUCTURE_FIELD_OPEN}|https?://|www\.|[A-Fa-f0-9]{{32,40}}\b)",
            val,
            re.I,
        )
        if m_next:
            val = val[: m_next.start()].strip()
        if len(val) > 48:
            val = val[:48].rstrip()
    elif _is_title_field_label(label):
        # 片名常带装饰前缀/嵌套括号，放宽长度
        if len(val) > 255:
            val = val[:255].rstrip()
    elif len(val) > 200:
        # 非密码字段被整页吞入时硬顶，避免描述爆炸
        val = val[:200].rstrip()
    return val


def _is_bogus_meta_value(key: str, val: str) -> bool:
    """抽样见到的脏结构值：残片种子名、预览写成下载/购买文案。"""
    k = (key or "").strip()
    v = (val or "").strip()
    if not k or not v:
        return True
    if k in TORRENT_FIELD_FORMS or k in {"种子名称", "種子名稱"}:
        if _BOGUS_TORRENT_NAME_RE.fullmatch(v):
            return True
        # 极短 ASCII 残片才丢；中文短片名（如「油鬼子」3 字）合法
        if len(v) < 2:
            return True
        if (
            len(v) < 4
            and not re.search(r"[\u4e00-\u9fffぁ-んァ-ン]", v)
            and not re.fullmatch(r"\d{1,3}", v)
        ):
            return True
    if any(h in k for h in ("预览", "預覽", "截图", "截圖")):
        if _BOGUS_PREVIEW_META_RE.search(v):
            return True
    return False


def _canonicalize_meta_key(key: str, aliases: dict[str, str] | None = None) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if aliases and k in aliases:
        return aliases[k]
    if k in DESCRIPTION_LABEL_ALIASES:
        return DESCRIPTION_LABEL_ALIASES[k]
    return k


# 转帖区等常用【影片说明】：无码 代替【是否有码】；仅短枚举才提升，避免长简介误入
_CODED_NOTE_KEYS = (
    "影片说明",
    "影片說明",
    "资源说明",
    "資源說明",
    "说明",
    "說明",
)
_CODED_STATUS_RE = re.compile(
    r"^(?:有码|无码|有碼|無碼|素人|(?:有|无|無)码(?:破解|中字|中文字幕)?)$"
)


def _looks_like_coded_status(value: str) -> bool:
    v = (value or "").strip()
    if not v or len(v) > 16:
        return False
    # 模板占位「有/无码」「有无码」不算实填
    if "/" in v or "有无" in v or "有無" in v:
        return False
    return bool(_CODED_STATUS_RE.fullmatch(v))


def _promote_coded_from_notes(meta: dict[str, str]) -> dict[str, str]:
    """【影片说明】：无码 → 是否有码（已有是否有码则不动）。"""
    if not meta or meta.get("是否有码"):
        return meta
    for k in _CODED_NOTE_KEYS:
        raw = meta.get(k)
        if not raw:
            continue
        val = _clip_field_value(raw, short_enum=True, label="是否有码")
        if _looks_like_coded_status(val):
            out = dict(meta)
            out["是否有码"] = val
            return out
    return meta


def normalize_metadata_for_board(
    metadata: dict[str, str] | None,
    board_fid: str | int | None = None,
) -> dict[str, str]:
    """按板块别名把繁简/异写键归一；去掉明显脏值。便于片名/大小精准入库。"""
    profile = description_profile_for_board(board_fid)
    aliases = dict(profile.get("aliases") or {})
    # 2048：额外并入全局别名里「大小/密码」类，避免漏繁体
    if str(board_fid or "").split(":", 1)[0] in _PW_2048_FIDS:
        for src, dst in DESCRIPTION_LABEL_ALIASES.items():
            aliases.setdefault(src, dst if dst != "资源大小" else "影片大小")
            if dst == "资源大小":
                aliases[src] = "影片大小"
            elif dst == "资源类型" and src in {"影片格式", "檔案格式", "文件格式"}:
                aliases[src] = "影片格式"
            elif dst == "资源名称" and src in {
                "影片标题",
                "影片標題",
                "影片名称",
                "影片名稱",
                "影片名",
            }:
                aliases[src] = "影片名称"
    out: dict[str, str] = {}
    for raw_key, raw_val in (metadata or {}).items():
        if _is_bogus_meta_value(raw_key, raw_val):
            continue
        key = _canonicalize_meta_key(raw_key, aliases)
        if not key or any(h in key for h in _HASH_META_LABEL_HINTS):
            # 裸 hash 标签只用于转磁力，不进结构化元数据
            continue
        if key in TORRENT_FIELD_FORMS or key in {"种子名称", "種子名稱"}:
            # 种子文件名不是子资源标题，不进展示元数据
            continue
        # 裁剪模式按「原始键或归一键」任一是否片名/大小字段决定，避免繁体片名被当普通字段截断
        clip_label = (
            raw_key
            if raw_key in _SIZE_FIELD_LABELS or _is_title_field_label(raw_key)
            else (
                key
                if key in _SIZE_FIELD_LABELS or _is_title_field_label(key)
                else raw_key
            )
        )
        val = _clip_field_value(
            raw_val,
            password=key == "解压密码" or raw_key in _PASSWORD_LABELS,
            short_enum=key in _SHORT_ENUM_LABELS or raw_key in _SHORT_ENUM_LABELS,
            label=clip_label,
        )
        if not val or _is_bogus_meta_value(key, val):
            continue
        out.setdefault(key, val)
    return _promote_coded_from_notes(out)


def extract_metadata(text: str) -> dict[str, str]:
    # 只折叠括号内标签字间空，保留取值里的「真·名」；再用字面标签匹配。
    blob = collapse_structure_label_gaps(text or "")
    meta: dict[str, str] = {}
    for m in LABEL_RE.finditer(blob):
        key = normalize_structure_label_key(m.group(1) or "")
        is_pwd = key in _PASSWORD_LABELS
        val = _clip_field_value(
            m.group(2),
            password=is_pwd,
            short_enum=key in _SHORT_ENUM_LABELS,
            label=key,
        )
        if key and val and not _is_bogus_meta_value(key, val):
            meta[key] = val
    return meta


def _is_bogus_password(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    if _EMAIL_PROTECTED_RE.search(v):
        return True
    # 剥离标签后残留的 CF 占位
    if re.fullmatch(r"\[?\s*email\s*protected\s*\]?", v, flags=re.I):
        return True
    if re.match(r"\[?\s*email\b", v, flags=re.I):
        return True
    # 「密码是 xxx」误把系词当成密码
    if re.fullmatch(r"[是为的了吧啊喔呢]", v):
        return True
    # 明显把半页正文吞进来了
    if len(v) > 120:
        return True
    if v.count("【") >= 1:
        return True
    if "下载附件" in v or "ed2k://" in v.lower() or "magnet:?" in v.lower():
        return True
    chinese = len(re.findall(r"[\u4e00-\u9fff]", v))
    if chinese >= 6:
        return True
    return False


def _normalize_password_value(value: str) -> str:
    """粘回被 HTML 拆开的 www.98T.la @ → www.98T.la@。"""
    v = (value or "").strip()
    if not v:
        return ""
    v = re.sub(r"((?:www\.)?98[Tt]\.la)\s*@", r"\1@", v)
    # 纯 98T 密码去掉中间空白
    compact = re.sub(r"\s+", "", v)
    if re.fullmatch(r"(?:www\.)?98[Tt]\.la@?", compact, flags=re.I):
        return compact
    return v


def extract_password(text: str, metadata: dict[str, str] | None = None) -> str:
    meta = metadata or {}
    for key in _PASSWORD_META_KEYS:
        val = _normalize_password_value(
            _clip_field_value(meta.get(key) or "", password=True)
        )
        # 【解压密码】：是www.xxx → 剥掉行首系词
        if val.startswith(("是", "为")) and len(val) > 1:
            val = _normalize_password_value(
                _clip_field_value(val[1:], password=True)
            )
        if val and not _is_bogus_password(val):
            return val
    blob = text or ""
    m = PASSWORD_RE.search(blob)
    if m:
        val = _normalize_password_value(
            _clip_field_value(m.group(1), password=True)
        )
        if val and not _is_bogus_password(val):
            return val
    m2 = PASSWORD_BARE_98T_RE.search(blob)
    if m2:
        val = _normalize_password_value(
            _clip_field_value(m2.group(1), password=True)
        )
        if val and not _is_bogus_password(val):
            return val
    return ""


def build_structured_description(
    metadata: dict[str, str] | None,
    *,
    extract_password: str = "",
    title: str = "",
    board_fid: str | int | None = None,
) -> str:
    """按板块结构卡片字段拼描述；不输出预览/附件/楼层等。"""
    profile = description_profile_for_board(board_fid)
    labels: tuple[str, ...] = tuple(profile["labels"])
    aliases: dict[str, str] = dict(profile.get("aliases") or {})
    exclusive: tuple[tuple[str, ...], ...] = tuple(profile.get("exclusive") or ())
    title_as = str(profile.get("title_as") or "资源名称")
    allowed = set(labels)

    # 未 normalize 的原文也可能只写【影片说明】：无码
    src_meta = _promote_coded_from_notes(dict(metadata or {}))

    picked: dict[str, str] = {}
    for raw_key, raw_val in src_meta.items():
        key = aliases.get(raw_key, raw_key)
        if key not in allowed or key in picked:
            continue
        is_pwd = key == "解压密码" or raw_key in _PASSWORD_LABELS
        clip_label = (
            raw_key
            if raw_key in _SIZE_FIELD_LABELS or _is_title_field_label(raw_key)
            else (
                key
                if key in _SIZE_FIELD_LABELS or _is_title_field_label(key)
                else raw_key
            )
        )
        val = _clip_field_value(
            raw_val,
            password=is_pwd,
            short_enum=key in _SHORT_ENUM_LABELS,
            label=clip_label,
        )
        if is_pwd and _is_bogus_password(val):
            continue
        if val:
            picked[key] = val

    pwd = _clip_field_value(extract_password, password=True)
    if pwd and not _is_bogus_password(pwd) and "解压密码" in allowed and "解压密码" not in picked:
        picked["解压密码"] = pwd

    if title_as in allowed and title_as not in picked:
        t = " ".join((title or "").split()).strip()
        if t:
            picked[title_as] = t[:300]

    # 互斥组：只保留组内第一个有值的键
    drop: set[str] = set()
    for group in exclusive:
        hit = next((k for k in group if k in picked), None)
        if hit:
            for k in group:
                if k != hit:
                    drop.add(k)
    for k in drop:
        picked.pop(k, None)

    return "\n".join(f"【{label}】：{picked[label]}" for label in labels if label in picked)


def _normalize_preview_url(base_url: str, src: str) -> str | None:
    src = (src or "").strip()
    if not src or src.startswith("data:"):
        return None
    # 相对路径必须有 base 才能拼成绝对地址；没有就不收，避免脏相对路径进库
    if not re.match(r"^(?:https?:)?//", src, re.I) and not base_url:
        return None
    full = urljoin(base_url or "", src) if base_url else src
    if full.startswith("//"):
        full = "https:" + full
    lowered = full.lower()
    if not lowered.startswith(("http://", "https://")):
        return None
    if any(marker in lowered for marker in IMAGE_SKIP_MARKERS):
        return None
    # 站内极小图标 / 1x1 之类不算预览
    if re.search(r"(?:_icon|icon_)\.(?:gif|png|jpe?g|webp)(?:\?|$)", lowered):
        return None
    # 文件名里带二维码/头像关键词
    path_only = lowered.split("?", 1)[0]
    if re.search(
        r"(?:^|/)(?:qr|qrcode|weixin.?qr|wx.?qr|avatar|noavatar|logo)(?:[_-]|\.|$)",
        path_only,
    ):
        return None
    return full


def _img_tag_is_noise(attrs: str) -> bool:
    """头像 / 在线标 / 勋章 / 二维码说明 / 过小图标。"""
    raw = attrs or ""
    if _IMG_NOISE_CLASS_RE.search(raw) or _IMG_NOISE_ID_RE.search(raw):
        return True
    for m in re.finditer(
        r"""(?:alt|title)\s*=\s*["']([^"']*)["']""",
        raw,
        re.I,
    ):
        if _IMG_NOISE_LABEL_RE.search(m.group(1) or ""):
            return True
    dims = [int(x) for x in _IMG_WH_RE.findall(raw)]
    # 两侧都不超过 120：多半是头像、图标、小二维码角标
    if len(dims) >= 2 and max(dims[:2]) <= 120 and min(dims[:2]) <= 120:
        return True
    if len(dims) == 1 and dims[0] <= 80:
        return True
    return False


def extract_preview_images(html: str, limit: int = 5, *, base_url: str = "") -> list[str]:
    """提取帖内预览图：有几张取几张，最多 limit（默认 5）；过滤表情/头像/二维码/论坛图标。

    属性优先级：Discuz zoomfile/file → PHPWind data-original 等懒加载 → src。
    若存在 inpost/aid/zoomfile 正文图，只收这类，避免签名档/侧栏装饰图。
    """
    blob = _STRIP_PREVIEW_BLOCKS_RE.sub(" ", html or "")
    candidates: list[tuple[str, bool]] = []  # (url, is_content)
    seen: set[str] = set()
    for tag in IMG_TAG_RE.finditer(blob):
        attrs = tag.group(1) or ""
        if _img_tag_is_noise(attrs):
            continue
        by_name: dict[str, str] = {}
        for m in IMG_ATTR_RE.finditer(attrs):
            attr_name = m.group(0).split("=", 1)[0].strip().lower()
            by_name[attr_name] = m.group(1).strip()
        src = (
            by_name.get("zoomfile")
            or by_name.get("file")
            or by_name.get("data-original")
            or by_name.get("data-src")
            or by_name.get("data-lazy-src")
            or by_name.get("data-lazy")
            or by_name.get("data-url")
            or by_name.get("src")
            or ""
        )
        url = _normalize_preview_url(base_url, src)
        if not url or url in seen:
            continue
        attrs_l = attrs.lower()
        is_content = bool(
            re.search(r"""\binpost\s*=\s*["']?1["']?""", attrs_l)
            or re.search(r"""\baid\s*=\s*["']?\d+""", attrs_l)
            or "zoomfile" in by_name
            or ("file" in by_name and "zoom" in attrs_l)
        )
        seen.add(url)
        candidates.append((url, is_content))

    preferred = [u for u, content in candidates if content]
    pick = preferred if preferred else [u for u, _ in candidates]
    return pick[: max(1, int(limit or 5))]


# 子标题切分：认 SUBRESOURCE_TITLE_MATCH_FORMS；匹配前折叠括号内标签字间空
_SUBRESOURCE_TITLE_ALT = structure_labels_alt(SUBRESOURCE_TITLE_MATCH_FORMS)
_SUBRESOURCE_TITLE_RE = re.compile(
    STRUCTURE_FIELD_OPEN
    + r"\s*(?:"
    + _SUBRESOURCE_TITLE_ALT
    + r")\s*"
    + STRUCTURE_FIELD_CLOSE,
    re.I,
)

# 子标题标签后的取值（到下一已知结构字段 / 磁力 / 结尾；保留片名里嵌套装饰）
_SUBRESOURCE_TITLE_VALUE_RE = re.compile(
    rf"^\s*{_STRUCTURE_SEP}\s*(.+?)(?=\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE}|\s*magnet:|\s*ed2k:|\s*$)",
    re.I | re.S,
)


def iter_subresource_title_spans(html: str) -> list[tuple[int, int]]:
    """返回每个真正子标题标签的 (start, end) 位置，按文档顺序。

    用括号扫描 + 归一键比对，避免 flexible 正则，且位置仍落在原文上。
    """
    blob = html or ""
    wanted = {normalize_structure_label_key(x) for x in SUBRESOURCE_TITLE_MATCH_FORMS}
    out: list[tuple[int, int]] = []
    for op, cl in (
        ("【", "】"),
        ("［", "］"),
        ("〖", "〗"),
        ("「", "」"),
        ("『", "』"),
        ("[", "]"),
    ):
        pat = re.compile(
            re.escape(op)
            + r"([^"
            + re.escape(cl)
            + r"\n]{1,40})"
            + re.escape(cl)
        )
        for m in pat.finditer(blob):
            if normalize_structure_label_key(m.group(1)) in wanted:
                out.append((m.start(), m.end()))
    out.sort(key=lambda x: x[0])
    return out


def iter_size_field_spans(html: str) -> list[tuple[int, int]]:
    """返回【影片大小】/【资源大小】等容量标签 (start, end)，文档序。

    2048 国产合集常见：无【影片名称】，仅多段【影片大小】+ 多磁力。
    """
    blob = html or ""
    wanted = {normalize_structure_label_key(x) for x in SIZE_FIELD_FORMS}
    out: list[tuple[int, int]] = []
    for op, cl in (
        ("【", "】"),
        ("［", "］"),
        ("〖", "〗"),
        ("「", "」"),
        ("『", "』"),
        ("[", "]"),
    ):
        pat = re.compile(
            re.escape(op)
            + r"([^"
            + re.escape(cl)
            + r"\n]{1,40})"
            + re.escape(cl)
        )
        for m in pat.finditer(blob):
            if normalize_structure_label_key(m.group(1)) in wanted:
                out.append((m.start(), m.end()))
    out.sort(key=lambda x: x[0])
    return out


def _name_before_size_label(
    scope: str,
    label_start: int,
    *,
    thread_title: str = "",
) -> str:
    """容量标签前的短文案作子名（国产合集无【影片名称】时）。"""
    window = scope[max(0, label_start - 240) : label_start]
    text = re.sub(r"<[^>]+>", " ", window or "")
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    # 去掉上一结构字段尾巴
    text = re.sub(
        r"^.*?(?:【[^】]{1,40}】|［[^］]{1,40}］)\s*[:：]?\s*",
        "",
        text,
    ).strip()
    # 取末段短句
    for sep in ("。", "！", "？", "\n", "；", ";"):
        if sep in text:
            text = text.rsplit(sep, 1)[-1].strip()
    text = text.strip(" ，,、·•|-")
    if len(text) < 4:
        return ""
    from parsers.resource_names import clip_subresource_display_name

    name = clip_subresource_display_name(text) or text
    name = _drop_thread_title_lines(name, thread_title) or name
    if thread_title and name.strip() == thread_title.strip():
        return ""
    return name[:120]


def _magnet_positions_in_scope(scope: str, wanted: set[str] | None = None) -> list[tuple[str, int, int]]:
    """兼容旧名：文档序磁力/电驴位置；(hash, start, end)。"""
    return _link_positions_in_scope(scope, wanted)


def _link_positions_in_scope(scope: str, wanted: set[str] | None = None) -> list[tuple[str, int, int]]:
    """文档序资源链位置；(hash, start, end)。同 hash 留首次。含 magnet + ed2k。"""
    pos: list[tuple[str, int, int]] = []
    seen_h: set[str] = set()
    for m in re.finditer(
        r"magnet:\?xt=urn:btih:([A-Fa-f0-9]{40}|[A-Fa-f0-9]{32}|[a-zA-Z2-7]{32})",
        scope,
        re.I,
    ):
        h = m.group(1).upper()
        if h in seen_h:
            continue
        seen_h.add(h)
        pos.append((h, m.start(), m.end()))
    for m in re.finditer(
        r"ed2k://\|file\|[^\|\n]{1,300}\|\d+\|([A-Fa-f0-9]{32})\|",
        scope,
        re.I,
    ):
        h = m.group(1).upper()
        if h in seen_h:
            continue
        seen_h.add(h)
        pos.append((h, m.start(), m.end()))
    if wanted:
        upper = scope.upper()
        for h in wanted:
            if h in seen_h:
                continue
            idx = upper.find(h)
            if idx < 0:
                continue
            seen_h.add(h)
            start = scope.rfind("magnet:", max(0, idx - 40), idx)
            if start < 0:
                start = scope.rfind("ed2k:", max(0, idx - 80), idx)
            if start < 0:
                start = idx
            pos.append((h, start, idx + len(h)))
    pos.sort(key=lambda x: x[1])
    return pos


def _detect_magnet_title_layout(
    titles: list[tuple[int, int]],
    mag_pos: list[tuple[str, int, int]],
) -> str:
    """识别合集切段布局。

    - title_then_magnet：【影片名称】→大小/截图→磁力（BT 合集常见，如 tid 3580931）
    - magnet_then_title：磁力→【影片名称】→截图（旧合集/测试样例）
    """
    if not titles or not mag_pos:
        return "magnet_then_title"
    if mag_pos[0][1] < titles[0][0]:
        return "magnet_then_title"
    return "title_then_magnet"


def _is_names_then_links_layout(
    titles: list[tuple[int, int]],
    link_pos: list[tuple[str, int, int]],
) -> bool:
    """连续 N 个资源名称后，再出现 N 个链接 → 按顺序 1:1。

    判定：标题簇内无链；首链在最后一个标题标签之后。
    """
    if len(titles) < 2 or not link_pos:
        return False
    cluster_lo = titles[0][0]
    cluster_hi = titles[-1][0]
    for _h, s, _e in link_pos:
        if cluster_lo <= s < cluster_hi:
            return False
    return link_pos[0][1] >= titles[-1][1]


def _size_from_subresource_block(scope: str, label_end: int, next_start: int) -> int:
    """从本子标题段内取【影片大小】/【资源大小】或片名里的 [MP4/ 899M] / 13V 66.7GB。"""
    from parsers.magnet import parse_capacity_bytes

    chunk = scope[label_end:next_start]
    chunk = re.sub(r"<[^>]+>", " ", chunk or "")
    chunk = re.sub(r"&nbsp;", " ", chunk, flags=re.I)
    return parse_capacity_bytes(chunk)


def _block_field(chunk: str, *labels: str) -> str:
    """从子资源块文本取结构字段（不含子标题本身）。"""
    if not chunk or not labels:
        return ""
    # 折叠括号内标签字间空后用字面标签；保留值区间隔号
    chunk = collapse_structure_label_gaps(chunk or "")
    alts = structure_labels_alt(list(labels))
    if not alts:
        return ""
    m = re.search(
        rf"{STRUCTURE_FIELD_OPEN}\s*(?:{alts})\s*{STRUCTURE_FIELD_CLOSE}\s*{_STRUCTURE_SEP}\s*"
        rf"(.+?)(?="
        rf"\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE}"
        rf"|{_ANY_STRUCTURE_BRACKET_LABEL_RE.pattern}\s*[:：︰﹒．.｜|/／·・•‧＝=]"
        rf"|\s*magnet:|\s*ed2k:|\s*$)",
        chunk,
        re.I | re.S,
    )
    if not m:
        return ""
    val = re.sub(r"<[^>]+>", " ", m.group(1) or "")
    val = re.sub(r"&nbsp;", " ", val, flags=re.I)
    val = re.sub(r"\s+", " ", val).strip()
    val = re.sub(r"^[:：﹒．.|｜/\\]+", "", val)
    val = re.sub(r"[:：﹒．.|｜/\\]+$", "", val)
    return val[:200]


_RE_2048_TORRENT_PAREN = re.compile(
    r"\(\s*2048[^)]*?torrent\s*\)\s*([^\s【(][^【\n]{0,120})",
    re.I,
)


def _title_from_2048_torrent_paren(text: str | None) -> str:
    """`(2048 hk-… torrent)油鬼子` → 油鬼子。"""
    m = _RE_2048_TORRENT_PAREN.search(text or "")
    if not m:
        return ""
    val = (m.group(1) or "").strip()
    val = re.split(r"\s*【", val, 1)[0].strip()
    val = re.sub(r"(?i)(?:\.torrent|\s+torrent)\s*$", "", val).strip()
    if not val or _is_bogus_meta_value("种子名称", val):
        return ""
    return val[:255]


def _torrent_name_as_title(raw: str | None) -> str:
    """无【影片名称】时，用可用的【种子名称】作子资源名（去掉 .torrent / 实体）。"""
    val = html_lib.unescape((raw or "").strip())
    val = re.sub(r"\s+", " ", val).strip()
    if not val:
        return ""
    # 2048 正文常把「【磁力连接】」/ magnet-box CSS 粘在种子名后
    val = re.split(r"\s*【", val, 1)[0].strip()
    val = re.split(r"\s*\.magnet-", val, 1)[0].strip()
    # 偶发整段写成 (2048 … torrent)片名
    paren = _title_from_2048_torrent_paren(val)
    if paren:
        return paren
    m = re.search(r"([^\s【】][^【】]{0,200}?)\.torrent\b", val, re.I)
    if m:
        val = m.group(1).strip()
    else:
        # 2048 三级写真常见「油鬼子 torrent」（无点号）
        val = re.sub(r"(?i)(?:\.torrent|\s+torrent)\s*$", "", val).strip()
    val = re.sub(r"^[:：﹒．.|｜/\\]+", "", val)
    val = re.sub(r"[:：﹒．.|｜/\\]+$", "", val).strip()
    if not val or _is_bogus_meta_value("种子名称", val):
        return ""
    return val[:255]


@dataclass(slots=True)
class SubresourceBlock:
    """合集中一条完整子资源块（名称→大小→格式→说明→截图→种子→磁力）。"""

    infohash: str
    title: str
    size: int = 0
    format: str = ""
    note: str = ""
    torrent_name: str = ""
    preview_images: list[str] = field(default_factory=list)
    description: str = ""


def _title_label_kind(scope: str, t_start: int, t_end: int) -> str:
    """子标题标签口径：film | resource（简繁/异写均认；字间空格先折叠）。"""
    raw = scope[t_start:t_end] or ""
    m = re.search(r"【\s*([^】]+?)\s*】", raw)
    lab = normalize_structure_label_key(m.group(1) if m else raw)
    resource_keys = {normalize_structure_label_key(x) for x in RESOURCE_TITLE_FORMS}
    film_keys = {normalize_structure_label_key(x) for x in FILM_TITLE_FORMS}
    if lab in resource_keys:
        return "resource"
    if lab in film_keys:
        return "film"
    # 片名是「影片名称」子串，不能用 contains；仅完整标签兜底
    if any(x in lab for x in ("资源", "資源", "作品")):
        return "resource"
    return "film"


def _build_block_description(
    *,
    title: str,
    size_label: str,
    fmt: str,
    note: str,
    kind: str = "film",
) -> str:
    """按子标题口径输出块描述：影片* 或 资源*。"""
    if kind == "resource":
        name_k, size_k, fmt_k, note_k = "资源名称", "资源大小", "资源类型", "资源说明"
    else:
        name_k, size_k, fmt_k, note_k = "影片名称", "影片大小", "影片格式", "影片说明"
    lines: list[str] = []
    if title:
        lines.append(f"【{name_k}】：{title}")
    if size_label:
        lines.append(f"【{size_k}】：{size_label}")
    if fmt:
        lines.append(f"【{fmt_k}】：{fmt}")
    if note:
        # 是否有码等短枚举仍用原文键更贴切时，统一进说明行
        lines.append(f"【{note_k}】：{note}")
    return "\n".join(lines)


def _assemble_subresource_block(
    *,
    paired: str,
    name: str,
    scope: str,
    field_lo: int,
    field_hi: int,
    kind: str,
    lim: int,
    base_url: str,
    preview_chunk: str | None = None,
) -> SubresourceBlock:
    raw_chunk = scope[field_lo:field_hi]
    text_chunk = re.sub(r"<[^>]+>", " ", raw_chunk or "")
    text_chunk = re.sub(r"&nbsp;", " ", text_chunk, flags=re.I)
    size = _size_from_subresource_block(scope, field_lo, field_hi)
    size_label = _block_field(text_chunk, *SIZE_FIELD_FORMS)
    if size_label:
        # 再裁一次：字间插空未折叠 / 未知尾字段时，只留容量串
        size_label = _clip_field_value(size_label, label="影片大小")
    if not size_label and size > 0:
        emb = re.search(
            r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
            name,
            re.I,
        )
        if emb:
            size_label = f"{emb.group(1)}{emb.group(2).upper()}"
    fmt = _block_field(text_chunk, *FORMAT_FIELD_FORMS)
    note = _block_field(text_chunk, *NOTE_FIELD_FORMS)
    torrent = _block_field(text_chunk, *TORRENT_FIELD_FORMS)
    imgs = extract_preview_images(
        preview_chunk if preview_chunk is not None else raw_chunk,
        limit=lim,
        base_url=base_url,
    )
    desc = _build_block_description(
        title=name,
        size_label=size_label,
        fmt=fmt,
        note=note,
        kind=kind,
    )
    return SubresourceBlock(
        infohash=paired,
        title=name,
        size=size,
        format=fmt,
        note=note,
        torrent_name=torrent,
        preview_images=imgs,
        description=desc,
    )


def extract_subresource_blocks(
    html: str,
    infohashes: list[str] | None = None,
    *,
    base_url: str = "",
    limit_per: int = 5,
    fallback_title: str = "",
) -> list[SubresourceBlock]:
    """按子标题切段挂资源链。返回 blocks；布局码见 extract_subresource_blocks_ex。"""
    blocks, _layout = extract_subresource_blocks_ex(
        html,
        infohashes,
        base_url=base_url,
        limit_per=limit_per,
        fallback_title=fallback_title,
    )
    return blocks


def extract_subresource_blocks_ex(
    html: str,
    infohashes: list[str] | None = None,
    *,
    base_url: str = "",
    limit_per: int = 5,
    fallback_title: str = "",
) -> tuple[list[SubresourceBlock], str]:
    """同 extract_subresource_blocks，并返回 layout 码。

    layout:
      - no_subtitle
      - no_subtitle_pack
      - names_then_links
      - title_then_magnet
      - magnet_then_title
      - size_then_magnet
      - empty
    """
    # 楼主各层（一楼元数据 + 二楼补链）拼成切段语料；路人回帖仍排除
    lz_parts = extract_lz_posts_html(html, limit=5)
    scope = "\n".join(lz_parts) if lz_parts else (extract_first_postmessage_html(html) or (html or ""))
    if not scope.strip():
        scope = html or ""

    wanted: set[str] | None = None
    if infohashes is not None:
        wanted = {(h or "").strip().upper() for h in infohashes if (h or "").strip()}
        if not wanted:
            return [], "empty"

    link_pos = _link_positions_in_scope(scope, wanted)
    if wanted:
        link_pos = [x for x in link_pos if x[0] in wanted]
    if not link_pos:
        return [], "empty"

    titles = iter_subresource_title_spans(scope)
    lim = max(1, int(limit_per or 5))
    out: list[SubresourceBlock] = []
    seen: set[str] = set()
    name_fallback = (fallback_title or "").strip()[:255]

    # 无子标题：多段【影片大小】+ 多链 → 按容量标签切段（2048 国产合集）
    # 若已有多段【种子名称】，走下方 no_subtitle 种子名路径，勿抢切。
    if not titles:
        size_spans = iter_size_field_spans(scope)
        seed_n = len(
            re.findall(
                r"【\s*种子名称|【\s*種子名稱|【\s*种子名稱|【\s*種子名称",
                scope,
            )
        )
        if len(size_spans) >= 2 and len(link_pos) >= 2 and seed_n < 2:
            layout_sz = _detect_magnet_title_layout(size_spans, link_pos)
            for i, (s_start, s_end) in enumerate(size_spans):
                next_start = (
                    size_spans[i + 1][0] if i + 1 < len(size_spans) else len(scope)
                )
                prev_end = size_spans[i - 1][1] if i > 0 else 0
                name = _name_before_size_label(
                    scope, s_start, thread_title=name_fallback
                )
                if not name:
                    # 容量值本身不够当名；用「合集片段 i」避免全并到帖标题
                    name = f"{name_fallback or '合集'}·{i + 1}"
                    name = name[:120]
                if layout_sz == "title_then_magnet":
                    mag_lo, mag_hi = s_start, next_start
                else:
                    mag_lo, mag_hi = prev_end, s_start
                in_seg = [
                    (h, s, e)
                    for h, s, e in link_pos
                    if mag_lo <= s < mag_hi and h not in seen
                ]
                if not in_seg:
                    continue
                first_h, _fs, first_end = in_seg[0]
                seen.add(first_h)
                out.append(
                    _assemble_subresource_block(
                        paired=first_h,
                        name=name,
                        scope=scope,
                        field_lo=s_end,
                        field_hi=next_start,
                        kind="film",
                        lim=lim,
                        base_url=base_url,
                    )
                )
                for h, _s, _e in in_seg[1:]:
                    if h in seen:
                        continue
                    seen.add(h)
                    last = out[-1]
                    out.append(
                        SubresourceBlock(
                            infohash=h,
                            title=last.title,
                            size=last.size,
                            format=last.format,
                            note=last.note,
                            torrent_name=last.torrent_name,
                            preview_images=list(last.preview_images),
                            description=last.description,
                        )
                    )
            if out:
                # 未配对的尾巴链挂到最后一名
                last = out[-1]
                for h, _s, _e in link_pos:
                    if h in seen:
                        continue
                    seen.add(h)
                    out.append(
                        SubresourceBlock(
                            infohash=h,
                            title=last.title,
                            size=last.size,
                            format=last.format,
                            note=last.note,
                            torrent_name=last.torrent_name,
                            preview_images=list(last.preview_images),
                            description=last.description,
                        )
                    )
                return out, "size_then_magnet"

    # 无子标题：多 hash 全部保留；有【种子名称】则作子资源名，否则回落帖标题
    if not titles:
        if not name_fallback and not link_pos:
            return [], "empty"
        # 大合集无子标题：一名共享预览，禁止逐链装配（962 链可从数十秒降到毫秒级）
        _PACK_FAST_MIN = 48
        if len(link_pos) >= _PACK_FAST_MIN and name_fallback:
            pack_size = _size_from_subresource_block(scope, 0, min(len(scope), 8000))
            previews = extract_preview_images(scope, limit=lim, base_url=base_url)
            from parsers.resource_names import clip_subresource_display_name

            name = clip_subresource_display_name(name_fallback) or name_fallback
            name = name[:255]
            desc = _build_block_description(
                title=name, size_label="", fmt="", note="", kind="film"
            )
            for h, _s, _e in link_pos:
                if h in seen:
                    continue
                seen.add(h)
                out.append(
                    SubresourceBlock(
                        infohash=h,
                        title=name,
                        size=pack_size,
                        format="",
                        note="",
                        torrent_name="",
                        preview_images=list(previews),
                        description=desc,
                    )
                )
            return out, "no_subtitle_pack"

        # 预览布局：图在磁力前（欧美/亚洲验证全码合集） vs 磁力后（测试/部分自拍）
        first_start = link_pos[0][1]
        img_then_magnet = bool(
            extract_preview_images(scope[:first_start], limit=1, base_url=base_url)
        )
        prev_end = 0
        for i, (h, start, end) in enumerate(link_pos):
            if h in seen:
                continue
            seen.add(h)
            next_start = (
                link_pos[i + 1][1] if i + 1 < len(link_pos) else len(scope)
            )
            # 种子名在磁力前（驗證全碼→种子名称→磁力）；窗口含上一段尾到下一链前
            field_lo, field_hi = prev_end, next_start
            raw_chunk = scope[field_lo:field_hi]
            text_chunk = re.sub(r"<[^>]+>", " ", raw_chunk or "")
            text_chunk = re.sub(r"&nbsp;", " ", text_chunk, flags=re.I)
            torr = _block_field(text_chunk, *TORRENT_FIELD_FORMS)
            name = _torrent_name_as_title(torr) or name_fallback
            if not name:
                continue
            from parsers.resource_names import clip_subresource_display_name

            name = clip_subresource_display_name(name) or name
            name = _drop_thread_title_lines(name, name_fallback) or name
            if img_then_magnet:
                preview_chunk = scope[prev_end:start]
            else:
                preview_chunk = scope[end:next_start]
            out.append(
                _assemble_subresource_block(
                    paired=h,
                    name=name,
                    scope=scope,
                    field_lo=field_lo,
                    field_hi=field_hi,
                    kind="film",
                    lim=lim,
                    base_url=base_url,
                    preview_chunk=preview_chunk,
                )
            )
            prev_end = end
        return out, "no_subtitle"

    # 连续名称 → 连续链接：1:1
    if _is_names_then_links_layout(titles, link_pos):
        n_pair = min(len(titles), len(link_pos))
        shared_tail = scope[titles[-1][1] : link_pos[0][1]]
        for i in range(n_pair):
            t_start, t_end = titles[i]
            next_start = titles[i + 1][0] if i + 1 < len(titles) else link_pos[0][1]
            name = _subresource_title_value(
                scope, t_end, next_start, label_start=t_start, thread_title=name_fallback
            )
            if not name:
                continue
            h = link_pos[i][0]
            if h in seen:
                continue
            seen.add(h)
            # 预览：标题簇后到首链前的公共图 + 本链到下一链之间的图
            link_end = link_pos[i][2]
            next_link = link_pos[i + 1][1] if i + 1 < len(link_pos) else len(scope)
            preview_chunk = shared_tail + scope[link_end:next_link]
            out.append(
                _assemble_subresource_block(
                    paired=h,
                    name=name,
                    scope=scope,
                    field_lo=t_end,
                    field_hi=next_start,
                    kind=_title_label_kind(scope, t_start, t_end),
                    lim=lim,
                    base_url=base_url,
                    preview_chunk=preview_chunk,
                )
            )
        # 多出的链接挂到最后一个已配对名称
        if out and len(link_pos) > n_pair:
            last = out[-1]
            for h, _s, _e in link_pos[n_pair:]:
                if h in seen:
                    continue
                seen.add(h)
                out.append(
                    SubresourceBlock(
                        infohash=h,
                        title=last.title,
                        size=last.size,
                        format=last.format,
                        note=last.note,
                        torrent_name=last.torrent_name,
                        preview_images=list(last.preview_images),
                        description=last.description,
                    )
                )
        return out, "names_then_links"

    layout = _detect_magnet_title_layout(titles, link_pos)

    for i, (t_start, t_end) in enumerate(titles):
        next_start = titles[i + 1][0] if i + 1 < len(titles) else len(scope)
        prev_end = titles[i - 1][1] if i > 0 else 0
        name = _subresource_title_value(
            scope, t_end, next_start, label_start=t_start, thread_title=name_fallback
        )
        if not name:
            continue

        # 字段区：本标题值之后 → 下一标题之前（最后到文尾）
        field_lo, field_hi = t_end, next_start
        # 链归属：
        # - 名称在前：本标题起 → 下一标题前
        # - 链在前：上一标题结束 → 本标题起（旧布局）
        if layout == "title_then_magnet":
            mag_lo, mag_hi = t_start, next_start
        else:
            mag_lo, mag_hi = prev_end, t_start

        in_seg = [
            (h, s, e) for h, s, e in link_pos if mag_lo <= s < mag_hi and h not in seen
        ]
        if not in_seg:
            continue

        kind = _title_label_kind(scope, t_start, t_end)
        # 段内链默认同名；若后续链前另有【种子名称】/（2048…torrent）片名则拆条
        # （三级写真常见：上一条【影片名称】后夹一条仅种子名的「油鬼子」）
        first_h, _fs, first_end = in_seg[0]
        seen.add(first_h)
        head = _assemble_subresource_block(
            paired=first_h,
            name=name,
            scope=scope,
            field_lo=field_lo,
            field_hi=field_hi,
            kind=kind,
            lim=lim,
            base_url=base_url,
        )
        out.append(head)
        prev_end = first_end
        for h, s, e in in_seg[1:]:
            seen.add(h)
            gap = scope[prev_end:s]
            gap_text = re.sub(r"<[^>]+>", " ", gap or "")
            gap_text = re.sub(r"&nbsp;", " ", gap_text, flags=re.I)
            alt = _torrent_name_as_title(
                _block_field(gap_text, *TORRENT_FIELD_FORMS)
            ) or _title_from_2048_torrent_paren(gap_text)
            if alt and alt != name:
                out.append(
                    _assemble_subresource_block(
                        paired=h,
                        name=alt,
                        scope=scope,
                        field_lo=prev_end,
                        field_hi=e,
                        kind=kind,
                        lim=lim,
                        base_url=base_url,
                    )
                )
            else:
                out.append(
                    SubresourceBlock(
                        infohash=h,
                        title=head.title,
                        size=head.size,
                        format=head.format,
                        note=head.note,
                        torrent_name=head.torrent_name,
                        preview_images=list(head.preview_images),
                        description=head.description,
                    )
                )
            prev_end = e
    return out, layout


def _drop_thread_title_lines(name: str, thread_title: str) -> str:
    """去掉子名里粘贴的合集帖标题行/前缀（最强優片等常见：标题换行+真片名）。"""
    import html as html_lib

    text = html_lib.unescape((name or "").strip())
    title = (thread_title or "").strip()
    if not text:
        return ""
    # 保留换行语义：先按行筛
    lines = [re.sub(r"^[:：﹒．.|｜/\\]+", "", ln).strip() for ln in re.split(r"[\r\n]+", text)]
    lines = [ln for ln in lines if ln]
    if title and len(lines) >= 2:
        kept = [ln for ln in lines if ln != title and not ln.startswith(title + " ")]
        if kept:
            text = " ".join(kept).strip()
        else:
            text = " ".join(lines).strip()
    else:
        text = " ".join(lines).strip() if lines else text
    if title and text.startswith(title):
        rest = text[len(title) :].lstrip(" \t-|:：﹒．.")
        if len(rest) >= 4:
            text = rest
    return text.strip()


def _subresource_title_value(
    scope: str,
    label_end: int,
    next_start: int,
    *,
    label_start: int | None = None,
    thread_title: str = "",
) -> str:
    """取【影片名称】/【资源名称】/【影片名称代号】标签后的片名。"""
    from parsers.resource_names import clip_subresource_display_name

    chunk = scope[label_end:next_start]
    # 保留换行，便于去掉「帖标题\n真片名」双行污染
    chunk = re.sub(r"<br\s*/?>", "\n", chunk or "", flags=re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = re.sub(r"&nbsp;", " ", chunk, flags=re.I)
    chunk = collapse_structure_label_gaps(chunk)
    m = _SUBRESOURCE_TITLE_VALUE_RE.match(chunk.strip())
    if not m:
        return ""
    name = (m.group(1) or "").strip()
    name = re.sub(r"^[:：﹒．.|｜/\\]+", "", name)
    name = re.sub(r"[:：﹒．.|｜/\\]+$", "", name)
    name = _drop_thread_title_lines(name, thread_title)
    # 名称代号后常接【可爱标签】营销文；代号类在首个【处截断，避免吞整段文案
    label_blob = ""
    if label_start is not None and 0 <= label_start < label_end <= len(scope):
        label_blob = re.sub(r"<[^>]+>", "", scope[label_start:label_end])
    if any(x in label_blob for x in ("代号", "代號", "原文", "原片", "套图", "套圖")):
        cut = re.search(r"\s*【", name)
        if cut:
            name = name[: cut.start()].strip()
    return clip_subresource_display_name(name)[:255]


def pair_magnet_to_subresource_title(
    html: str,
    infohashes: list[str],
) -> dict[str, str]:
    """子标题 ↔ 磁力配对（自动识别名称在前或磁力在前）。"""
    meta = pair_magnet_to_subresource_meta(html, infohashes)
    return {h: title for h, (title, _size) in meta.items() if title}


def pair_magnet_to_subresource_meta(
    html: str,
    infohashes: list[str],
) -> dict[str, tuple[str, int]]:
    """返回 infohash → (子标题, 字节大小)。整块字段同源，见 extract_subresource_blocks。"""
    return {
        b.infohash: (b.title, int(b.size or 0))
        for b in extract_subresource_blocks(html, infohashes)
        if b.title
    }


def extract_preview_images_by_infohash(
    html: str,
    infohashes: list[str],
    *,
    base_url: str = "",
    limit_per: int = 5,
) -> dict[str, list[str]]:
    """按子资源块挂预览图（与名称/大小/磁力同一块）。"""
    out: dict[str, list[str]] = {}
    for b in extract_subresource_blocks(
        html, infohashes, base_url=base_url, limit_per=limit_per
    ):
        if b.preview_images:
            out[b.infohash] = list(b.preview_images)
    if out:
        return out

    # 无真正子标题时：退回按磁力切段
    # 楼主各层（一楼元数据 + 二楼补链）拼成切段语料；路人回帖仍排除
    lz_parts = extract_lz_posts_html(html, limit=5)
    scope = "\n".join(lz_parts) if lz_parts else (extract_first_postmessage_html(html) or (html or ""))
    if not scope.strip():
        scope = html or ""
    wanted = {(h or "").strip().upper() for h in infohashes if (h or "").strip()}
    if not wanted:
        return {}
    mag_pos = _magnet_positions_in_scope(scope, wanted)
    lim = max(1, limit_per)
    for i, (h, _start, end) in enumerate(mag_pos):
        if h not in wanted:
            continue
        next_start = mag_pos[i + 1][1] if i + 1 < len(mag_pos) else min(len(scope), end + 2500)
        imgs = extract_preview_images(scope[end:next_start], limit=lim, base_url=base_url)
        if imgs:
            out[h] = imgs
    return out


def extract_blockcode_text(html: str) -> str:
    parts: list[str] = []
    for m in BLOCKCODE_RE.finditer(html or ""):
        parts.append(_clean_text(m.group(1)))
    return "\n".join(parts)


def parse_thread_content(html: str, tid: int = 0, *, base_url: str = "") -> ThreadContent:
    """Build structured content from raw thread HTML (no link parsing)."""
    title = extract_title(html)
    # 元数据 / 密码只从一楼抽；预览图仍看整页（含附件注入的图）
    op_html = extract_first_postmessage_html(html)
    plain = _clean_text(op_html)
    block = extract_blockcode_text(op_html)
    if not block:
        # 一楼无 blockcode：再扫主贴语料（含附件注入），勿扫回帖
        corpus = extract_link_corpus_html(html)
        if corpus:
            block = extract_blockcode_text(corpus)
    combined = f"{plain}\n{block}"
    metadata = extract_metadata(combined)
    return ThreadContent(
        tid=extract_tid(html, fallback=tid),
        title=title,
        plain_text=plain,
        blockcode_text=block,
        metadata=metadata,
        # 优先一楼/楼主正文，避免扫进页眉页脚 UI 图（PHPWind 尤其明显）
        preview_images=extract_preview_images(op_html or html, limit=5, base_url=base_url),
        extract_password=extract_password(combined, metadata),
    )
