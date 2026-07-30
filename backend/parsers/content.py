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

# 每资源预览图上限（帖级 / 块内 / 入库截断同一口径）
PREVIEW_IMAGE_LIMIT = 6

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
        # 正文【资源名称】与 title_as 灌入的【影片名称】（常带「2048独家合集」版头）互斥，
        # 保留资源名称（tid=27097301：影片名称=假版头+真名，资源名称=真名）。
        "exclusive": (("资源名称", "影片名称"), ("影片时间", "影片时长")),
        "aliases": _PW_2048_BT_ALIASES,
        "title_as": "影片名称",
    }


_RE_2048_EXCLUSIVE_TITLE_PREFIX = re.compile(r"^2048\s*独家合集\s+", re.I)


def strip_2048_exclusive_title_prefix(title: str) -> str:
    """去掉最新合集帖标题版头「2048独家合集」，避免当子资源名。"""
    t = " ".join((title or "").split()).strip()
    if not t:
        return ""
    stripped = _RE_2048_EXCLUSIVE_TITLE_PREFIX.sub("", t).strip()
    return stripped or t


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
# 预览类字段若是下载页/购买提示/纯磁链导语/附件列表噪声，则丢弃（勿当结构字段入库）
_BOGUS_PREVIEW_META_RE = re.compile(
    r"(?:"
    r"rmdown\.com|购买本帖|立即购买|购买人名单|需向作者支付"
    r"|下载磁链|磁力链接\s*$|磁力連接"
    r"|下载附件|下载次数|点击文件名下载"
    r"|\.png\s*\(|\.jpe?g\s*\(|\.gif\s*\(|\.webp\s*\("
    r"|aid=\d+"
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

# 枚举型短字段：取值到首个空白/标点为止，避免一楼边界失败时吞进回复/营销行
_SHORT_ENUM_LABELS = frozenset(
    {
        "资源类型",
        "資源類型",
        "是否有码",
        "是否有碼",
        "有无码",
        "有無碼",
        "影片码别",
        "有无第三方水印",
        "有無第三方水印",
        "有无水印",
        "有無水印",
        "第三方水印",
        "影片格式",
        "影片有无声音",
        "影片有無聲音",
        "有无声音",
        "有無聲音",
        "影片有无聲音",
    }
)
_SHORT_ENUM_VALUE_RE = re.compile(r"^([^\s，,。；;|/]+)")
# 「解压密码是www.98T.la@」——「是/为」是系词不是密码；也兼容冒号/等号
# 另有【资源密码】写法（】与冒号之间可无空格）
# 帖内常见简写「解压码：」（无「密」字）；www.98T.la 与 @ 常被拆成链接+彩色字
_PASSWORD_ASCII_TOKEN = (
    r"(?:www\.)?98[Tt]\.la\s*@?|[A-Za-z0-9][A-Za-z0-9@._\-]{2,79}"
)
# 人眼可见的短中文口令（排除「错误/私信」等提示词，见 _is_bogus_password）
_PASSWORD_CN_TOKEN = r"[\u4e00-\u9fffA-Za-z0-9@._\-]{2,16}"
_PASSWORD_NOT_HINT = r"(?!(?:错误|不对|忘記|忘记|私信|看图|看圖|见下|見下|同上|没有|沒有))"

PASSWORD_RE = re.compile(
    r"(?:解压|提取|资源|解壓|資源)\s*密?\s*码\s*】?\s*(?:[:：=]|是|为)?\s*"
    rf"{_PASSWORD_NOT_HINT}"
    rf"({_PASSWORD_ASCII_TOKEN}|[^\s【】\n，,。；;]+)",
    re.I,
)
# 帖内常见：单独「密码/码」后跟 www.98T.la@（无解压/提取前缀，常夹在 font 标签里）
PASSWORD_BARE_98T_RE = re.compile(
    rf"(?:密码|密碼|码|碼)\s*(?:[:：=]|是|为)?\s*((?:www\.)?98[Tt]\.la\s*@?)",
    re.I,
)
# 人一眼能认：密码：/密码是/密码 sakura / 密码sakura99（可无冒号，但值须像口令）
PASSWORD_GENERIC_RE = re.compile(
    rf"(?:密码|密碼|pass(?:word)?|pwd)\s*(?:[:：=]|是|为)?\s*"
    rf"{_PASSWORD_NOT_HINT}"
    rf"({_PASSWORD_ASCII_TOKEN}|{_PASSWORD_CN_TOKEN})",
    re.I,
)
# 「解压用/解压请用」后直接跟口令（仅 ASCII/98T，避免吞「这个」）
PASSWORD_UNZIP_USE_RE = re.compile(
    rf"(?:解压|解壓)\s*(?:用|请用|請用)\s*[:：]?\s*"
    rf"({_PASSWORD_ASCII_TOKEN})",
    re.I,
)
_PASSWORD_META_KEYS = ("解压密码", "提取密码", "资源密码", "解压码", "提取码", "资源码")
_PASSWORD_LABELS = frozenset(_PASSWORD_META_KEYS)
# 口令结束：换行 / 下一【标签】 / 标点 / 链 / 附件 UI / 空格+中文说明 / ASCII后紧贴中文
_PASSWORD_END_RE = re.compile(
    r"(?:"
    r"\n"
    r"|【"
    r"|[，,。．；;、！!？?]"
    r"|(?:ed2k://|magnet:\?)"
    r"|(?:下载附件|下载次数|点击文件名下载|阅读权限\s*:)"
    r"|\s+\S+\.(?:rar|zip|7z|txt|docx?|xlsx?|xls|torrent|jpe?g|png|gif|bmp|webp|mp4|mkv|avi)\b"
    r"|\s+[\u4e00-\u9fff]"
    r"|(?<=[A-Za-z0-9@.])[\u4e00-\u9fff]"
    r")",
    re.I,
)
# 完整 98T 口令优先整段收下（避免被后续噪声拉长）
_PASSWORD_98T_HEAD_RE = re.compile(
    r"^((?:www\.)?98[Tt]\.la\s*@?|[0-9A-Za-z._\-]+@(?:www\.)?98[Tt]\.la)",
    re.I,
)
# 人一看就不是解压口令的提示词
_BOGUS_PASSWORD_WORDS = frozenset(
    {
        "错误",
        "不对",
        "忘记",
        "忘記",
        "私信",
        "看图",
        "看圖",
        "见下",
        "見下",
        "见楼",
        "見樓",
        "同上",
        "如下",
        "上面",
        "下面",
        "没有",
        "沒有",
        "无",
        "空",
        "自取",
        "附图",
        "附圖",
        "本帖",
        "回帖",
        "积分",
        "積分",
        "金币",
        "金幣",
        "这个",
        "這個",
        "那个",
        "那個",
    }
)
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
    # 块级/换行标签 → 真换行（Discuz 一字段一行常用 </div><div>，勿收成空格）
    text = re.sub(
        r"(?i)<br\s*/?>|</p\s*>|</div\s*>|</li\s*>|</tr\s*>|</h[1-6]\s*>",
        "\n",
        text,
    )
    text = re.sub(
        r"(?i)<(?:p|div|li|tr|h[1-6])\b[^>]*>",
        "\n",
        text,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = _EMAIL_PROTECTED_RE.sub(" ", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_title(html: str) -> str:
    """取页面帖标题；仅剥「B 【影片名称】：」类内嵌标签，其余按页面原文。

    不做正文补全、专辑头替换。仅去掉 HTML 标签/实体；
    退到 <title> 时再去站名后缀。
    """
    m = re.search(r'id="thread_subject"[^>]*>(.*?)</(?:a|span|div)>', html, re.I | re.S)
    if m:
        title = _clean_text(m.group(1)).strip()
    else:
        # PHPWind 常见 subject_tpc
        m = re.search(
            r'id="subject_tpc"[^>]*>(.*?)</(?:a|span|div|h\d)>',
            html,
            re.I | re.S,
        )
        if m:
            title = _clean_text(m.group(1)).strip()
        else:
            m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            if not m:
                return ""
            # <title> 常带「片名 - 论坛名」
            title = _strip_forum_title_suffix(_clean_text(m.group(1)))
    from parsers.resource_names import unwrap_subject_film_title
    from parsers.thread_gates import close_trailing_capacity_bracket

    return close_trailing_capacity_bracket(unwrap_subject_film_title(title))


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


def first_floor_name_label_count(html: str) -> int:
    """一楼（物理首帖 / 首层楼主帖）上的子资源名称标签数。"""
    body = extract_first_postmessage_html(html) or ""
    if not body.strip():
        parts = extract_lz_posts_html(html, limit=1)
        body = parts[0] if parts else ""
    if not body.strip():
        return 0
    return len(iter_subresource_title_spans(body))


def should_scan_lz_multi_floor(html: str) -> bool:
    """单资源看楼主多楼；多资源只看一楼。

    **先有名称、再抽链：** 一楼名称标签 0～1 → 单资源（可二楼补链）；
    ≥2 → 多资源（名称已齐，链/切块均不扫二楼及以后）。
    """
    return first_floor_name_label_count(html) <= 1


def extract_link_corpus_html(
    html: str, *, limit: int = 5, multi_floor: bool | None = None
) -> str:
    """链接语料：单资源=楼主各层（含二楼补链）；多资源=仅一楼 + 附件。

    multi_floor:
      - None：按一楼名称标签数自动判定（0～1 开多楼，≥2 关）
      - True / False：强制开/关多楼

    路人回帖默认不参与；仅当下列情形且楼主正文无 magnet/ed2k 时，
    才补入含目标链的回帖（避免讨论帖/网盘帖被回帖链误入库）：
    - 标题/楼主明示「求磁力」类；或
    - 标题/楼主宣称 115/ED2K/电驴（楼主常只贴网盘，链在回帖补，如 tid=3300074）。

    已注入附件且附件内含目标链时：链语料以附件为准（正文样例链不并入）。
    """
    use_multi = should_scan_lz_multi_floor(html) if multi_floor is None else bool(multi_floor)
    floor_limit = max(1, int(limit or 5)) if use_multi else 1
    lz_parts: list[str] = list(extract_lz_posts_html(html, limit=floor_limit))
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
    # 标题/楼主宣称 115/ED2K/电驴，但楼主正文无 magnet/ed2k（常只贴网盘，链在回帖补）
    # tid=3300074：【夸克/115eD2k】+夸克正文，回帖 blockcode 才有 ed2k
    claims_ed2k = bool(
        re.search(
            r"115\s*e?d2k|【[^】]{0,48}(?:115|e?d2k|电驴)[^】]{0,48}】|(?<![A-Za-z0-9])e?d2k(?![A-Za-z0-9])|电驴",
            ask_blob,
            re.I,
        )
    )
    if not has_body_link and (asks_for_link or claims_ed2k):
        # 楼主无目标链：扫回帖补 magnet/ed2k（限量）
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

    下一字段按「结构卡片开标签」切（任意角色/带分隔的未知标签），不靠白名单。
    片名保留无分隔的装饰【合集】。
    密码字段走 clip_password_value（保留换行结束边界）。
    """
    if password:
        return clip_password_value(value or "")

    from parsers.structure_cards import find_next_structure_field_start

    # 2048/转帖常见：变体选择符、全角冒号前缀
    val = (value or "").replace("\r", "\n")
    val = re.sub(r"[\ufe0e\ufe0f\u200d\u200b\u200c\u200d]", "", val)
    val = " ".join(val.split())
    val = val.lstrip(":：︰.").strip()
    if not val:
        return ""

    is_size = label in _SIZE_FIELD_LABELS or label in SIZE_FIELD_FORMS
    # 大小值常再包装饰【4.92GB/8V/8配额】：须先剥壳，再跑下一【标签】截断，
    # 否则 _NEXT_FIELD_RE 在起点把整段切空（tid=3659150）
    if is_size:
        from parsers.magnet import unwrap_decorative_capacity_value

        val = unwrap_decorative_capacity_value(val)
        if not val:
            return ""

    # 片名截断前折叠下一字段标签字间空
    if _is_title_field_label(label):
        val = collapse_structure_label_gaps(val)
        cut = find_next_structure_field_start(val, min_start=1)
        if cut is not None and cut > 0:
            val = val[:cut].strip()
    elif not is_size:
        # 非片名/非大小：遇任意开闭括号标签即截（装饰【】也断开说明/格式等短字段）
        m = _NEXT_FIELD_RE.search(val)
        if m:
            val = val[: m.start()].strip()
    noise = _FIELD_NOISE_RE.search(val)
    if noise:
        val = val[: noise.start()].strip()
    if short_enum:
        m3 = _SHORT_ENUM_VALUE_RE.match(val)
        if m3:
            val = m3.group(1).strip()
        if len(val) > 32:
            val = val[:32].rstrip()
    elif is_size:
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
        # 目录号合法：OM1 / JP12 / A3 等（勿因 len<4 误杀）
        if re.fullmatch(r"[A-Za-z]{1,6}\d{1,6}[A-Za-z]?", v):
            return False
        if (
            len(v) < 4
            and not re.search(r"[\u4e00-\u9fffぁ-んァ-ン]", v)
            and not re.fullmatch(r"\d{1,3}", v)
        ):
            return True
    if any(h in k for h in ("预览", "預覽", "截图", "截圖", "缩略图", "縮略圖")):
        if _BOGUS_PREVIEW_META_RE.search(v):
            return True
        # 附件区文件名行：98 (3).png / xxx.rar (1.01 MB
        if re.search(r"\.\w{2,4}\s*\(\s*[\d.]+\s*[KMGT]?B?", v, re.I):
            return True
    return False


def _canonicalize_meta_key(
    key: str,
    aliases: dict[str, str] | None = None,
    *,
    keep_keys: set[str] | frozenset[str] | None = None,
) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if aliases and k in aliases:
        return aliases[k]
    # 板块 profile 已列出的展示键勿被全局别名改掉（如 BT 的【影片容量】）
    if keep_keys and k in keep_keys:
        return k
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
    keep_keys = frozenset(profile.get("labels") or ())
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
        key = _canonicalize_meta_key(raw_key, aliases, keep_keys=keep_keys)
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
    """结构字段：先切卡片再取值（不依赖巨型标签白名单才能切开）。"""
    from parsers.structure_cards import cards_to_metadata_dict, parse_structure_cards

    cards = parse_structure_cards(text or "")
    raw = cards_to_metadata_dict(cards)
    meta: dict[str, str] = {}
    for key, raw_val in raw.items():
        is_pwd = key in _PASSWORD_LABELS or "密码" in key or "密碼" in key
        val = _clip_field_value(
            raw_val,
            password=is_pwd,
            short_enum=key in _SHORT_ENUM_LABELS,
            label=key,
        )
        if key and val and not _is_bogus_meta_value(key, val):
            meta[key] = val
    return meta


def clip_password_value(raw: str) -> str:
    """人写密码：标签后的口令吃到结束信号为止（完整提取、不吞说明）。

    结束信号：换行、下一【结构标签】、中英文标点、ed2k/magnet、
    附件 UI、空格+中文说明、粘在口令后的中文说明等。
    """
    if not (raw or "").strip():
        return ""
    val = (raw or "").replace("\r", "\n")
    val = re.sub(r"[\ufe0e\ufe0f\u200b\u200c\u200d]", "", val)
    # HTML 常把 www.98T.la 与 @ 拆成两行/两段
    val = re.sub(r"((?:www\.)?98[Tt]\.la)\s*\n\s*@", r"\1@", val)
    # 1) 换行结束（密码几乎总是单行；上一步已粘回跨行 @）
    val = val.split("\n", 1)[0].strip()
    if not val:
        return ""
    # 2) 去掉值前残留的冒号/系词（「是/为」在标签侧已剥，这里再兜底）
    val = re.sub(r"^[:：︰=.]+", "", val).strip()
    if val.startswith(("是", "为")) and len(val) > 1:
        val = val[1:].lstrip(":：︰= ").strip()
    if not val:
        return ""

    # 3) 优先整段 98T / xxx@98T.la（站方惯用）
    m98 = _PASSWORD_98T_HEAD_RE.match(val)
    if m98:
        head = m98.group(1)
        rest = val[m98.end() :]
        # 后面立刻是结束信号或结束 → 收下完整 98T
        if not rest or _PASSWORD_END_RE.match(rest) or rest[0] in " \t【":
            return _normalize_password_value(head)
        # 后面是字母数字续写（极少）再往下走统一截断

    # 4) 统一结束切点
    m_end = _PASSWORD_END_RE.search(val)
    if m_end and m_end.start() > 0:
        val = val[: m_end.start()].strip()
    elif m_end and m_end.start() == 0:
        return ""

    # 5) 下一结构字段（任意【…】开标签）
    try:
        from parsers.structure_cards import find_next_structure_field_start

        cut = find_next_structure_field_start(val, min_start=1)
        if cut is not None and cut > 0:
            val = val[:cut].strip()
    except Exception:
        m_br = re.search(r"【", val)
        if m_br and m_br.start() > 0:
            val = val[: m_br.start()].strip()

    # 6) 字段噪声（楼层/附件壳）
    noise = _FIELD_NOISE_RE.search(val)
    if noise and noise.start() > 0:
        val = val[: noise.start()].strip()

    val = _normalize_password_value(val)
    if len(val) > 80:
        val = val[:80].rstrip()
    return val


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
    if v in _BOGUS_PASSWORD_WORDS:
        return True
    if re.search(
        r"(?:错误|不对|私信|看图|看圖|见下|見下|忘记|忘記|积分|積分|金币|金幣)",
        v,
    ):
        return True
    # 明显把半页正文吞进来了
    if len(v) > 80:
        return True
    if v.count("【") >= 1:
        return True
    if "下载附件" in v or "ed2k://" in v.lower() or "magnet:?" in v.lower():
        return True
    chinese = len(re.findall(r"[\u4e00-\u9fff]", v))
    # 短中文口令人一眼能认；带句式虚词/过长才当说明文
    if chinese >= 1 and re.search(r"[的了吗呢吧啊喔，。；;]", v):
        return True
    if chinese >= 16:
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
    # 1998@www.98T.la 类：去掉符号两侧多余空白
    compact2 = re.sub(r"\s*@\s*", "@", compact)
    if re.fullmatch(
        r"[0-9A-Za-z._\-]+@(?:www\.)?98[Tt]\.la",
        compact2,
        flags=re.I,
    ):
        return compact2
    return v


def _accept_password_candidate(raw: str) -> str:
    """标签后的候选值 → 按人眼结束边界裁切 → 校验。"""
    val = clip_password_value(raw or "")
    if val and not _is_bogus_password(val):
        return val
    return ""


def extract_password(text: str, metadata: dict[str, str] | None = None) -> str:
    """单段语料抽密码（兼容旧调用）；多源请用 harvest_extract_password。"""
    return harvest_extract_password(text or "", metadata=metadata)


def harvest_extract_password(
    *parts: str,
    metadata: dict[str, str] | None = None,
) -> str:
    """多源收解压密码，避免只出现在文中某处时被漏掉。

    只认「标注后的口令」，不做裸 98T 猜测（预览附件名常带 www.98T.la@ 水印）。
    取值经 clip_password_value：吃到换行/下一标签/标点/链/附件 UI/中文说明为止。
    优先级（高→低）：
      1. metadata / 结构卡片 password 角色
      2. 「解压/提取/资源密码」标注
      3. 「密码：/密码是/密码xxx」（人一眼能认的提示）
      4. 「解压用/解压请用」+ ASCII/98T
      5. 「码/密码」+ 98T.la@
    语料会先走 _clean_text（还原 CF 邮箱混淆）。
    """
    meta = metadata or {}
    for key in _PASSWORD_META_KEYS:
        hit = _accept_password_candidate(meta.get(key) or "")
        if hit:
            return hit

    cleaned_parts: list[str] = []
    for part in parts:
        if not part or not str(part).strip():
            continue
        # 已是纯文本则 _clean_text 也安全；含 HTML 则还原 CF + 换行
        cleaned_parts.append(_clean_text(str(part)))
    blob = "\n".join(cleaned_parts)
    if not blob.strip():
        return ""
    # 标签与 98T/@ 被 HTML 拆开时先粘回，便于完整提取
    blob = re.sub(r"((?:www\.)?98[Tt]\.la)\s*\n\s*@", r"\1@", blob)
    blob = re.sub(r"((?:www\.)?98[Tt]\.la)\s+@", r"\1@", blob)

    # 结构卡片里的 password 角色（任意位置【解压密码】等）
    try:
        from parsers.structure_cards import parse_structure_cards

        for card in parse_structure_cards(blob):
            if card.role != "password":
                continue
            hit = _accept_password_candidate(card.value or "")
            if hit:
                return hit
    except Exception:
        pass

    for cre in (
        PASSWORD_RE,
        PASSWORD_GENERIC_RE,
        PASSWORD_UNZIP_USE_RE,
        PASSWORD_BARE_98T_RE,
    ):
        m = cre.search(blob)
        if not m:
            continue
        # 从捕获起点往后多取一段，再统一 clip（防正则 token 截短/吞说明）
        start = m.start(1)
        tail = blob[start : start + 160]
        hit = _accept_password_candidate(tail)
        if hit:
            return hit
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
        from parsers.resource_names import unwrap_subject_film_title

        t = unwrap_subject_film_title(" ".join((title or "").split()).strip())
        # 2048：title_as 用去版头后的标题；若已有资源名称则不再灌影片名称（交给 exclusive）
        if str(board_fid or "").split(":", 1)[0] in _PW_2048_FIDS:
            if "资源名称" in picked:
                t = ""
            else:
                t = strip_2048_exclusive_title_prefix(t)
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


def extract_preview_images(
    html: str, limit: int = PREVIEW_IMAGE_LIMIT, *, base_url: str = ""
) -> list[str]:
    """提取帖内预览图：有几张取几张，最多 limit（默认 PREVIEW_IMAGE_LIMIT）；过滤表情/头像/二维码/论坛图标。

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
    # 优先：紧邻容量前的最后一段【资源格式】（2048 国产常把简介写进格式当片名）
    fmt_matches = list(
        re.finditer(r"【\s*资源格式\s*】\s*[:：]?\s*([^\n【]{2,200})", text)
    )
    if fmt_matches:
        text = fmt_matches[-1].group(1).strip()
    else:
        # 取最后一个结构字段后的尾巴（勿停在中间的【下载网址】）
        last = None
        for m in re.finditer(
            r"(?:【[^】]{1,40}】|［[^］]{1,40}］)\s*[:：]?\s*",
            text,
        ):
            last = m
        if last:
            text = text[last.end() :].strip()
    # 取末段短句
    for sep in ("。", "！", "？", "\n", "；", ";"):
        if sep in text:
            text = text.rsplit(sep, 1)[-1].strip()
    text = text.strip(" ，,、·•|-")
    # 允许 2～3 字中文短片名（如「油鬼子」）；勿一律 len<4 丢弃
    from parsers.resource_names import (
        clip_subresource_display_name,
        is_acceptable_short_title,
        salvage_short_subresource_name,
    )

    if not is_acceptable_short_title(text) and len(text) < 4:
        return ""
    name = clip_subresource_display_name(text) or text
    if not name:
        name = salvage_short_subresource_name(text)
    if not name:
        return ""
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


def _block_field_value_unusable(val: str) -> bool:
    """空值 / 吃到下一字段标签（如【磁力连接）。"""
    v = (val or "").strip()
    if not v:
        return True
    if v.startswith("【") or v.startswith("［") or v.startswith("["):
        return True
    if re.match(r"(?:磁力|下载网址|下載網址|驗證|验证|种子名称|種子名稱)", v):
        return True
    return False


def _block_field(chunk: str, *labels: str, prefer_last: bool = False) -> str:
    """从子资源块文本取结构字段（不含子标题本身）。"""
    if not chunk or not labels:
        return ""
    # 折叠括号内标签字间空后用字面标签；保留值区间隔号
    chunk = collapse_structure_label_gaps(chunk or "")
    alts = structure_labels_alt(list(labels))
    if not alts:
        return ""
    matches = list(
        re.finditer(
            rf"{STRUCTURE_FIELD_OPEN}\s*(?:{alts})\s*{STRUCTURE_FIELD_CLOSE}\s*{_STRUCTURE_SEP}\s*"
            rf"(.+?)(?="
            rf"\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_LABEL_ALT})\s*{STRUCTURE_FIELD_CLOSE}"
            rf"|{_ANY_STRUCTURE_BRACKET_LABEL_RE.pattern}\s*[:：︰﹒．.｜|/／·・•‧＝=]"
            rf"|\s*magnet:|\s*ed2k:|\s*$)",
            chunk,
            re.I | re.S,
        )
    )
    if not matches:
        return ""
    ordered = reversed(matches) if prefer_last else matches
    for m in ordered:
        val = re.sub(r"<[^>]+>", " ", m.group(1) or "")
        val = re.sub(r"&nbsp;", " ", val, flags=re.I)
        val = re.sub(r"\s+", " ", val).strip()
        val = re.sub(r"^[:：﹒．.|｜/\\]+", "", val)
        val = re.sub(r"[:：﹒．.|｜/\\]+$", "", val)
        if _block_field_value_unusable(val):
            continue
        return val[:200]
    return ""



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


# [欧美无码] OM1 AccidentalGangbang... / [亚洲无码] JP3 ...
# 亦见 [欧美无码] 01 18Lust.24.06.19....（两位序号+片名，tid=27191175）
# HAT13057 等目录号可达 5～6 位数字（tid=25026517）
_CATALOG_BRACKET_TITLE_RE = re.compile(
    r"\[\s*[^\]]{1,24}\s*\]\s*"
    r"("
    r"(?:"
    r"[A-Za-z]{1,6}\d{1,6}\b"  # OM1 / JP12 / HAT13057
    r"|"
    r"\d{1,3}(?=\s+\S)"  # 01 + 片名
    r")"
    r"[^\n【]{0,160}"
    r")",
    re.I,
)


def _title_from_catalog_bracket_line(
    text: str | None, *, prefer_last: bool = False
) -> str:
    """无【影片名称】时，取「[分类] 目录号+片名」整行作子名。"""
    matches = list(_CATALOG_BRACKET_TITLE_RE.finditer(text or ""))
    if not matches:
        return ""
    m = matches[-1] if prefer_last else matches[0]
    return _clean_catalog_title_match(m.group(1) or "")


def _clean_catalog_title_match(raw: str) -> str:
    val = (raw or "").strip()
    val = re.sub(r"\[XvX\]\s*$", "", val, flags=re.I).strip()
    val = re.sub(r"\s+", " ", val).strip()
    if len(val) < 3:
        return ""
    return val[:255]


def _catalog_title_matching_torrent(text: str | None, torr_title: str) -> str:
    """种子名 HAT13057 时，取同号目录行全文（跳过前面的空壳 HAT13056）。"""
    code = (torr_title or "").strip().split()[0] if (torr_title or "").strip() else ""
    if len(code) < 3:
        return ""
    for m in reversed(list(_CATALOG_BRACKET_TITLE_RE.finditer(text or ""))):
        val = _clean_catalog_title_match(m.group(1) or "")
        if val and (val == code or val.startswith(code + " ") or val.startswith(code + "[")):
            return val
    return ""



@dataclass(slots=True)
class SubresourceBlock:
    """合集中一条完整子资源块（先切块，再块内卡片）。"""

    infohash: str
    title: str
    size: int = 0
    format: str = ""
    note: str = ""
    torrent_name: str = ""
    preview_images: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


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
        lines.append(f"【{note_k}】：{note}")
    return "\n".join(lines)


@dataclass(slots=True)
class BlockCardEnrichment:
    """块内卡片识别结果。"""

    title: str = ""
    size: int = 0
    size_label: str = ""
    format: str = ""
    note: str = ""
    torrent_name: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    description: str = ""


def enrich_block_with_cards(
    chunk_text: str,
    *,
    fallback_name: str = "",
    thread_title: str = "",
    kind: str = "film",
    board_fid: str | int | None = None,
) -> BlockCardEnrichment:
    """对单个资源块文本跑结构卡片，产出名/大小/描述等。"""
    from parsers.magnet import parse_capacity_bytes
    from parsers.resource_names import (
        clip_subresource_display_name,
        is_decoration_only_filename,
        is_dirty_filename,
        is_hard_dirty_filename,
        is_weak_subresource_name,
    )
    from parsers.structure_cards import (
        cards_to_metadata_dict,
        name_values_from_cards,
        parse_structure_cards,
    )

    text = _clean_text(chunk_text or "")
    cards = parse_structure_cards(text)
    raw_meta = cards_to_metadata_dict(cards)
    # 块内再 clip（与 extract_metadata 对齐）
    meta: dict[str, str] = {}
    for key, raw_val in raw_meta.items():
        is_pwd = key in _PASSWORD_LABELS or "密码" in key or "密碼" in key
        val = _clip_field_value(
            raw_val,
            password=is_pwd,
            short_enum=key in _SHORT_ENUM_LABELS,
            label=key,
        )
        if is_pwd:
            val = _normalize_password_value(val)
            if _is_bogus_password(val):
                continue
        if key and val and not _is_bogus_meta_value(key, val):
            meta[key] = val
    meta = normalize_metadata_for_board(meta, board_fid)

    names = name_values_from_cards(cards)
    title = ""
    if names:
        # 影片/资源口径：优先对应键
        if kind == "resource":
            for k in ("资源名称", "資源名稱", "作品名称", "套图名称", "套圖名稱"):
                if meta.get(k):
                    title = meta[k]
                    break
        else:
            for k in ("影片名称", "影片名稱", "影片名", "视频名称", "視頻名稱"):
                if meta.get(k):
                    title = meta[k]
                    break
        if not title:
            title = names[0]
    title = clip_subresource_display_name(title) or (title or "").strip()

    size_label = ""
    for k in (
        "资源大小",
        "資源大小",
        "影片大小",
        "影片容量",
        "文件大小",
        "檔案大小",
    ):
        if meta.get(k):
            size_label = meta[k]
            break
    if not size_label:
        for c in cards:
            if c.role == "size" and (c.value or "").strip():
                size_label = _clip_field_value(c.value, label="影片大小")
                break
    size = parse_capacity_bytes(size_label) if size_label else 0
    if size <= 0:
        size = parse_capacity_bytes(text)
    # 字节已从正文扫到、但标签值先前被装饰括号误切空：再 clip 一次补回 label→meta/描述
    if size > 0 and not size_label:
        for c in cards:
            if c.role != "size" or not (c.value or "").strip():
                continue
            recovered = _clip_field_value(c.value, label="影片大小")
            if recovered:
                size_label = recovered
                break
    if size_label:
        if kind == "resource":
            meta.setdefault("资源大小", size_label)
        else:
            meta.setdefault("影片大小", size_label)
            meta.setdefault("资源大小", size_label)

    fmt = ""
    if kind == "resource":
        fmt_keys = ("资源类型", "資源類型", "文件格式", "文件类型", "影片格式")
    else:
        fmt_keys = ("影片格式", "文件格式", "文件类型", "资源类型", "資源類型")
    for k in fmt_keys:
        if meta.get(k):
            fmt = meta[k]
            break
    note = meta.get("是否有码") or meta.get("影片说明") or meta.get("资源说明") or ""

    torrent = ""
    for c in cards:
        if c.role == "torrent" and (c.value or "").strip():
            torrent = (c.value or "").strip()
            break
    torr_title = _torrent_name_as_title(torrent)

    fb = (fallback_name or "").strip()
    post = (thread_title or "").strip()
    if not title or is_decoration_only_filename(title) or is_hard_dirty_filename(title):
        title = ""
    # 切块已抽出的名称（fallback）优先于块内种子名；仅当 fallback 弱名时才用种子名
    if title and is_weak_subresource_name(title, post_title=post):
        if fb and not is_weak_subresource_name(fb, post_title=post):
            title = fb
        elif torr_title:
            title = torr_title
    if not title:
        title = (
            clip_subresource_display_name(fb)
            or fb
            or torr_title
            or clip_subresource_display_name(post)
            or post
        )
    # 卡片名弱、但切段名强：仍用切段名（块文本常从标签后起，不含【影片名称】行）
    if (
        title
        and fb
        and is_weak_subresource_name(title, post_title=post)
        and not is_weak_subresource_name(fb, post_title=post)
    ):
        title = fb
    if (
        torr_title
        and title
        and title == torr_title
        and fb
        and not is_weak_subresource_name(fb, post_title=post)
        and fb != torr_title
    ):
        # 勿让同块后段【种子名称】盖掉本段【影片名称】
        title = fb
    title = clip_subresource_display_name(title) or title
    if title and (is_dirty_filename(title) or is_hard_dirty_filename(title)):
        alt = (
            clip_subresource_display_name(fb)
            or fb
            or torr_title
            or clip_subresource_display_name(post)
            or post
        )
        if alt and not is_hard_dirty_filename(alt):
            title = alt
    title = (title or "")[:255]

    # 切段名常落在标签之后，块内 cards 可能没有 name 键 → 补进 meta 供帖级描述
    if title:
        if kind == "resource":
            meta.setdefault("资源名称", title)
        else:
            meta.setdefault("影片名称", title)
            meta.setdefault("资源名称", title)

    # 片名装饰里的 [MP4/1.9GB]
    if not size_label and size <= 0 and title:
        emb = re.search(
            r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
            title,
            re.I,
        )
        if emb:
            size_label = f"{emb.group(1)}{emb.group(2).upper()}"
            size = parse_capacity_bytes(size_label)

    # 块描述：有板口径用 profile；密码从块 meta 带入
    block_pwd = extract_password("", meta)
    if board_fid is not None:
        desc = build_structured_description(
            meta,
            extract_password=block_pwd,
            title=title,
            board_fid=board_fid,
        )
    else:
        desc = ""
    if not desc:
        desc = _build_block_description(
            title=title,
            size_label=size_label,
            fmt=fmt,
            note=note,
            kind=kind,
        )
        if block_pwd and "解压密码" not in desc and "解壓密碼" not in desc:
            desc = (desc + f"\n【解压密码】：{block_pwd}").strip()

    return BlockCardEnrichment(
        title=title,
        size=int(size or 0),
        size_label=size_label or "",
        format=fmt or "",
        note=note or "",
        torrent_name=torrent or "",
        metadata=meta,
        description=desc,
    )


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
    thread_title: str = "",
    board_fid: str | int | None = None,
) -> SubresourceBlock:
    raw_chunk = scope[field_lo:field_hi]
    # 传入原始 HTML 块：enrich 内 _clean_text 会还原 CF 邮箱密码后再切卡片
    enriched = enrich_block_with_cards(
        raw_chunk,
        fallback_name=name,
        thread_title=thread_title,
        kind=kind,
        board_fid=board_fid,
    )
    # 容量：卡片优先，否则回落块内扫
    size = int(enriched.size or 0)
    if size <= 0:
        size = _size_from_subresource_block(scope, field_lo, field_hi)
    imgs = extract_preview_images(
        preview_chunk if preview_chunk is not None else raw_chunk,
        limit=lim,
        base_url=base_url,
    )
    return SubresourceBlock(
        infohash=paired,
        title=enriched.title or (name or "")[:255],
        size=size,
        format=enriched.format,
        note=enriched.note,
        torrent_name=enriched.torrent_name,
        preview_images=imgs,
        description=enriched.description,
        metadata=dict(enriched.metadata or {}),
    )


def _repair_missing_structure_open_brackets(scope: str) -> str:
    """补全偶发缺失的左【：如行首「套图名称】：」（tid=24506022）。

    勿在「【原文片名】」内把后缀「片名】」再包一层。
    """
    if not scope or "】" not in scope:
        return scope or ""
    from parsers.resource_names import SUBRESOURCE_TITLE_MATCH_FORMS

    # 子标题 + 常见块字段
    labels = list(SUBRESOURCE_TITLE_MATCH_FORMS) + [
        "图片数量",
        "圖片數量",
        "图片格式",
        "圖片格式",
        "文件大小",
        "檔案大小",
        "图片预览",
        "圖片預覽",
        "磁力连接",
        "磁力連結",
        "磁力链接",
        "下載網址",
        "下载网址",
    ]
    alt = "|".join(sorted({re.escape(x) for x in labels if x}, key=len, reverse=True))
    if not alt:
        return scope
    # 标签前不得已是【／汉字／字母（防【原文片名】被切成【原文【片名】）
    return re.sub(
        rf"(?<![【［\u4e00-\u9fffA-Za-z0-9])(?P<lab>{alt})】",
        lambda m: f"【{m.group('lab')}】",
        scope,
    )


def extract_subresource_blocks(
    html: str,
    infohashes: list[str] | None = None,
    *,
    base_url: str = "",
    limit_per: int = PREVIEW_IMAGE_LIMIT,
    fallback_title: str = "",
    board_fid: str | int | None = None,
) -> list[SubresourceBlock]:
    """按子标题切段挂资源链。返回 blocks；布局码见 extract_subresource_blocks_ex。"""
    blocks, _layout = extract_subresource_blocks_ex(
        html,
        infohashes,
        base_url=base_url,
        limit_per=limit_per,
        fallback_title=fallback_title,
        board_fid=board_fid,
    )
    return blocks


def extract_subresource_blocks_ex(
    html: str,
    infohashes: list[str] | None = None,
    *,
    base_url: str = "",
    limit_per: int = PREVIEW_IMAGE_LIMIT,
    fallback_title: str = "",
    board_fid: str | int | None = None,
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
    # 单资源：楼主各层（一楼元数据 + 二楼补链）；多资源：只看一楼，避免二楼串链
    if should_scan_lz_multi_floor(html):
        lz_parts = extract_lz_posts_html(html, limit=5)
        scope = (
            "\n".join(lz_parts)
            if lz_parts
            else (extract_first_postmessage_html(html) or (html or ""))
        )
    else:
        scope = extract_first_postmessage_html(html) or ""
        if not scope.strip():
            lz_parts = extract_lz_posts_html(html, limit=1)
            scope = lz_parts[0] if lz_parts else (html or "")
    if not scope.strip():
        scope = html or ""
    scope = _repair_missing_structure_open_brackets(scope)

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
    lim = max(1, int(limit_per or PREVIEW_IMAGE_LIMIT))
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
                        thread_title=name_fallback,
                        board_fid=board_fid,
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
                            metadata=dict(last.metadata or {}),
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
                            metadata=dict(last.metadata or {}),
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
            previews = extract_preview_images(scope, limit=lim, base_url=base_url)
            # 整帖一块：块内卡片（单资源大包）
            enriched = enrich_block_with_cards(
                scope[: min(len(scope), 24_000)],
                fallback_name=name_fallback,
                thread_title=name_fallback,
                kind="film",
                board_fid=board_fid,
            )
            name = (enriched.title or name_fallback)[:255]
            pack_size = int(enriched.size or 0) or _size_from_subresource_block(
                scope, 0, min(len(scope), 8000)
            )
            desc = enriched.description or _build_block_description(
                title=name, size_label="", fmt="", note="", kind="film"
            )
            meta = dict(enriched.metadata or {})
            for h, _s, _e in link_pos:
                if h in seen:
                    continue
                seen.add(h)
                out.append(
                    SubresourceBlock(
                        infohash=h,
                        title=name,
                        size=pack_size,
                        format=enriched.format,
                        note=enriched.note,
                        torrent_name=enriched.torrent_name,
                        preview_images=list(previews),
                        description=desc,
                        metadata=meta,
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
            # 种子名在磁力前；窗口到下一链前（兼容链后补字段）。空壳种子名靠 _block_field 跳过。
            field_lo, field_hi = prev_end, next_start
            raw_chunk = scope[field_lo:field_hi]
            text_chunk = re.sub(r"<[^>]+>", " ", raw_chunk or "")
            text_chunk = re.sub(r"&nbsp;", " ", text_chunk, flags=re.I)
            # 取首个可用种子名（跳过空壳）；再用种子号对齐目录行（跳过空壳目录）
            torr = _block_field(text_chunk, *TORRENT_FIELD_FORMS)
            torr_title = _torrent_name_as_title(torr)
            name = (
                _catalog_title_matching_torrent(text_chunk, torr_title)
                or _title_from_catalog_bracket_line(text_chunk)
                or torr_title
                or name_fallback
            )
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
                    thread_title=name_fallback,
                    board_fid=board_fid,
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
                    thread_title=name_fallback,
                    board_fid=board_fid,
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
                        metadata=dict(last.metadata or {}),
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
            thread_title=name_fallback,
            board_fid=board_fid,
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
                        thread_title=name_fallback,
                        board_fid=board_fid,
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
                        metadata=dict(head.metadata or {}),
                    )
                )
            prev_end = e
    return out, layout


def _drop_thread_title_lines(name: str, thread_title: str = "") -> str:
    """兼容旧调用：不再砍帖标题前缀，资源名原文保留（仅做空白规范化）。

    历史曾剥帖标题前缀，会把「帖标题，尾巴」砍成「，尾巴」丢主体（约六千条）。
    """
    import html as html_lib

    _ = thread_title  # 保留参数兼容旧调用
    text = html_lib.unescape((name or "").strip())
    if not text:
        return ""
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _subresource_title_value(
    scope: str,
    label_end: int,
    next_start: int,
    *,
    label_start: int | None = None,
    thread_title: str = "",
) -> str:
    """取【影片名称】/【资源名称】/【影片名称代号】标签后的片名。"""
    from parsers.resource_names import (
        clip_subresource_display_name,
        salvage_short_subresource_name,
    )

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
    raw_name = name
    name = re.sub(r"^[:：﹒．.|｜/\\]+", "", name)
    name = re.sub(r"[:：﹒．.|｜/\\]+$", "", name)
    name = _drop_thread_title_lines(name, thread_title)
    # 名称代号后常接【可爱标签】营销文；代号类在首个【处截断，避免吞整段文案
    label_blob = ""
    if label_start is not None and 0 <= label_start < label_end <= len(scope):
        label_blob = re.sub(r"<[^>]+>", "", scope[label_start:label_end])
    if any(x in label_blob for x in ("代号", "代號", "原文", "原片", "套图", "套圖")):
        # 截断「真名【营销标签】…」；勿砍掉以「【装饰前缀】」开头的片名
        # （tid=27268283：【套圖名稱】: 【重磅核弹】阿曼达…）
        cut = re.search(r"\s*【", name)
        if cut and cut.start() > 0:
            name = name[: cut.start()].strip()
    clipped = clip_subresource_display_name(name)
    if clipped:
        return clipped[:255]
    # clip 过空：抢救短中文/目录号，避免整段资源因「长度不足」被 continue 丢掉
    saved = salvage_short_subresource_name(name) or salvage_short_subresource_name(
        raw_name
    )
    return (saved or "")[:255]


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
    limit_per: int = PREVIEW_IMAGE_LIMIT,
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
    # 密码：一楼字段 + 楼主多层语料（二楼补链旁常写密码）一起收，免漏
    lz_corpus = extract_link_corpus_html(html)
    pwd = harvest_extract_password(
        combined,
        lz_corpus or "",
        metadata=metadata,
    )
    return ThreadContent(
        tid=extract_tid(html, fallback=tid),
        title=title,
        plain_text=plain,
        blockcode_text=block,
        metadata=metadata,
        # 优先一楼/楼主正文，避免扫进页眉页脚 UI 图（PHPWind 尤其明显）
        preview_images=extract_preview_images(
            op_html or html, limit=PREVIEW_IMAGE_LIMIT, base_url=base_url
        ),
        extract_password=pwd,
    )
