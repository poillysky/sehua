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
    SUBRESOURCE_TITLE_LABELS,
    SUBRESOURCE_TITLE_MATCH_FORMS,
    TORRENT_FIELD_FORMS,
)

# BT + ED2K board label styles commonly used on sehuatang（2026-07 抽样核对）
LABEL_KEYS = (
    *SUBRESOURCE_TITLE_MATCH_FORMS,
    "出演女优",
    "出演女優",
    *SIZE_FIELD_FORMS,
    *FORMAT_FIELD_FORMS,
    *NOTE_FIELD_FORMS,
    "有无水印",
    "有無浮水印",
    "有无第三方水印",
    "有無第三方浮水印",
    "第三方水印",
    "第三方浮水印",
    "解压密码",
    "解壓密碼",
    "提取密码",
    "提取密碼",
    "资源密码",
    "資源密碼",
    "种子期限",
    "種子期限",
    "下载方式",
    "下載方式",
    "下载工具",
    "下載工具",
    "时间长度",
    "時間長度",
    "影片有无声音",
    "影片有無聲音",
    "剧情连拍截图/缩略图",
    "劇情連拍截圖/縮略圖",
    "剧情连拍截图",
    "劇情連拍截圖",
    "资源预览",
    "資源預覽",
    "查重证明图",
    "查重證明圖",
    "前缀证明图",
    "前綴證明圖",
)

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
    "资源密码": "解压密码",
    "資源密碼": "解压密码",
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

_LABEL_ALT = "|".join(map(re.escape, LABEL_KEYS))
# 值截到下一个字段标签为止（同行/换行均可）。
# 「文件大小」等若不在白名单，旧逻辑整页揉在一起会导致解压密码吞到帖尾。
LABEL_RE = re.compile(
    rf"【\s*({_LABEL_ALT})\s*】\s*[:：]?\s*"
    rf"(.*?)(?="
    rf"(?:\s*【\s*(?:{_LABEL_ALT})\s*】)"  # 已知字段
    rf"|(?:\s*【[^】\n]{{1,40}}】\s*[:：])"  # 任意「【标签】：」
    rf"|$"
    rf")",
    re.I | re.S,
)

# 下一个字段边界（截密码/字段尾巴用）
_NEXT_FIELD_RE = re.compile(r"\s*【[^】]{1,40}】")
# 名称类字段值里常嵌套【自转】【合集】等，只能裁到「已知结构字段」
_KNOWN_NEXT_FIELD_RE = re.compile(rf"\s*【\s*(?:{_LABEL_ALT})\s*】", re.I)
_TITLE_FIELD_LABELS = frozenset(SUBRESOURCE_TITLE_LABELS)
_SIZE_FIELD_LABELS = frozenset({"资源大小", "文件大小", "影片大小", "影片容量"})
# 82V+173P/6.7G/1配额 · 70.6G/1169V//7配额 · 807 M / 1V
_SIZE_VALUE_RE = re.compile(
    r"^("
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
PASSWORD_RE = re.compile(
    r"(?:解压|提取|资源)\s*密码\s*】?\s*(?:[:：=]|是|为)?\s*([^\s【】\n，,。；;]+)",
    re.I,
)
# 帖内常见：单独「密码」后跟 www.98T.la@（无解压/提取前缀，常夹在 font 标签里）
PASSWORD_BARE_98T_RE = re.compile(
    r"密码\s*(?:[:：=]|是|为)?\s*((?:www\.)?98[Tt]\.la@?)",
    re.I,
)
_PASSWORD_META_KEYS = ("解压密码", "提取密码", "资源密码")
_PASSWORD_LABELS = frozenset(_PASSWORD_META_KEYS)
# 优先 zoomfile / file（Discuz 高清），再 src
IMG_TAG_RE = re.compile(r"<img\b([^>]*)>", re.I)
IMG_ATTR_RE = re.compile(
    r"""(?:zoomfile|file|src)\s*=\s*["']([^"']+)["']""",
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
        return _clean_text(m.group(1))
    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if m:
        return _clean_text(m.group(1)).split(" - ")[0].strip()
    return ""


def extract_tid(html: str, fallback: int = 0) -> int:
    m = re.search(r"tid[=:]?\s*['\"]?(\d+)", html, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"thread-(\d+)-1-\d+\.html", html, re.I)
    return int(m.group(1)) if m else fallback


def extract_first_postmessage_html(html: str) -> str:
    """只取一楼 postmessage 正文，避免把回复楼/页脚揉进元数据。"""
    src = html or ""
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


def extract_lz_posts_html(html: str, *, limit: int = 5) -> list[str]:
    """取带「楼主」标的各层 postmessage（一楼 + 楼主二楼补链等）。

    路人回帖不纳入。limit 限制最多纳入几层楼主帖。
    """
    src = html or ""
    if not src:
        return []

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
    """
    src = html or ""
    if not src:
        return ""

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
    """链接/子资源语料：楼主各层（含二楼补链）+ 附件注入块。路人回帖不参与。"""
    parts: list[str] = list(extract_lz_posts_html(html, limit=limit))
    # 附件下载后 inject_attachment_text 写入的块（非纯数字楼 id）
    for m in re.finditer(
        r'id=["\']postmessage_attach\d+["\'][^>]*>(.*?)</div>',
        html or "",
        re.I | re.S,
    ):
        body = (m.group(1) or "").strip()
        if body:
            parts.append(body)
    return "\n".join(parts)


def _clip_field_value(
    value: str,
    *,
    password: bool = False,
    short_enum: bool = False,
    label: str = "",
) -> str:
    """裁掉粘在后面的【下一字段】、附件区与楼层噪声。"""
    val = " ".join((value or "").replace("\r", "\n").split())
    val = val.lstrip(":：").strip()
    if not val:
        return ""
    # 名称可含嵌套【标签】；其它字段遇到任意【…】即截
    next_re = _KNOWN_NEXT_FIELD_RE if label in _TITLE_FIELD_LABELS else _NEXT_FIELD_RE
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
    elif label in _SIZE_FIELD_LABELS:
        # 大小后常跟博主导语（某房/颜值/合集…），只留容量串
        m4 = _SIZE_VALUE_RE.match(val)
        if m4:
            val = m4.group(1).strip().strip("/+-\u00d7xX \t")
        if len(val) > 48:
            val = val[:48].rstrip()
    elif len(val) > 200:
        # 非密码字段被整页吞入时硬顶，避免描述爆炸
        val = val[:200].rstrip()
    return val


def extract_metadata(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for m in LABEL_RE.finditer(text or ""):
        key = m.group(1).strip()
        is_pwd = key in _PASSWORD_LABELS
        val = _clip_field_value(
            m.group(2),
            password=is_pwd,
            short_enum=key in _SHORT_ENUM_LABELS,
            label=key,
        )
        if key and val:
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


def extract_password(text: str, metadata: dict[str, str] | None = None) -> str:
    meta = metadata or {}
    for key in _PASSWORD_META_KEYS:
        val = _clip_field_value(meta.get(key) or "", password=True)
        # 【解压密码】：是www.xxx → 剥掉行首系词
        if val.startswith(("是", "为")) and len(val) > 1:
            val = _clip_field_value(val[1:], password=True)
        if val and not _is_bogus_password(val):
            return val
    blob = text or ""
    m = PASSWORD_RE.search(blob)
    if m:
        val = _clip_field_value(m.group(1), password=True)
        if val and not _is_bogus_password(val):
            return val
    m2 = PASSWORD_BARE_98T_RE.search(blob)
    if m2:
        val = _clip_field_value(m2.group(1), password=True)
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

    picked: dict[str, str] = {}
    for raw_key, raw_val in (metadata or {}).items():
        key = aliases.get(raw_key, raw_key)
        if key not in allowed or key in picked:
            continue
        is_pwd = key == "解压密码" or raw_key in _PASSWORD_LABELS
        clip_label = raw_key if raw_key in _SIZE_FIELD_LABELS | _TITLE_FIELD_LABELS else key
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
    return full


def extract_preview_images(html: str, limit: int = 5, *, base_url: str = "") -> list[str]:
    """提取帖内预览图：有几张取几张，最多 limit（默认 5）；过滤表情/用户组等装饰图。"""
    urls: list[str] = []
    seen: set[str] = set()
    for tag in IMG_TAG_RE.finditer(html or ""):
        attrs = tag.group(1) or ""
        by_name: dict[str, str] = {}
        for m in IMG_ATTR_RE.finditer(attrs):
            attr_name = m.group(0).split("=", 1)[0].strip().lower()
            by_name[attr_name] = m.group(1).strip()
        # 优先 Discuz zoomfile/file（帖内大图）；纯 UI 小图通常只有 src
        src = by_name.get("zoomfile") or by_name.get("file") or by_name.get("src") or ""
        url = _normalize_preview_url(base_url, src)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= max(1, limit):
            break
    return urls


# 子标题切分：认 SUBRESOURCE_TITLE_MATCH_FORMS（简繁 影片名称/资源名称）
_SUBRESOURCE_TITLE_RE = re.compile(
    r"【\s*(?:" + "|".join(map(re.escape, SUBRESOURCE_TITLE_MATCH_FORMS)) + r")\s*】",
    re.I,
)

# 子标题标签后的取值（到下一结构键 / 磁力 / 结尾）
_SUBRESOURCE_TITLE_VALUE_RE = re.compile(
    r"^\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*ed2k:|\s*$)",
    re.I | re.S,
)


def iter_subresource_title_spans(html: str) -> list[tuple[int, int]]:
    """返回每个真正子标题标签的 (start, end) 位置，按文档顺序。"""
    return [(m.start(), m.end()) for m in _SUBRESOURCE_TITLE_RE.finditer(html or "")]


def _magnet_positions_in_scope(scope: str, wanted: set[str] | None = None) -> list[tuple[str, int, int]]:
    """文档序磁力位置；(hash, start, end)。同 hash 留首次。"""
    mag_pos: list[tuple[str, int, int]] = []
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
        mag_pos.append((h, m.start(), m.end()))
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
                start = idx
            mag_pos.append((h, start, idx + len(h)))
    mag_pos.sort(key=lambda x: x[1])
    return mag_pos


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


def _size_from_subresource_block(scope: str, label_end: int, next_start: int) -> int:
    """从本子标题段内取【影片大小】/【资源大小】或片名里的 [MP4/ 899M]。"""
    from parsers.magnet import _size_from_label

    chunk = scope[label_end:next_start]
    chunk = re.sub(r"<[^>]+>", " ", chunk or "")
    chunk = re.sub(r"&nbsp;", " ", chunk, flags=re.I)
    sm = re.search(
        r"【\s*(?:"
        + "|".join(map(re.escape, SIZE_FIELD_FORMS))
        + r")\s*】\s*[:：]?\s*([0-9.]+)\s*(T|TB|G|GB|M|MB|K|KB)?",
        chunk,
        re.I,
    )
    if sm:
        return _size_from_label(sm.group(1), sm.group(2))
    emb = re.search(
        r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
        chunk,
        re.I,
    )
    if emb:
        return _size_from_label(emb.group(1), emb.group(2))
    return 0


def _block_field(chunk: str, *labels: str) -> str:
    """从子资源块文本取结构字段（不含子标题本身）。"""
    if not chunk or not labels:
        return ""
    alts = "|".join(re.escape(x) for x in labels)
    m = re.search(
        rf"【\s*(?:{alts})\s*】\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*ed2k:|\s*$)",
        chunk,
        re.I | re.S,
    )
    if not m:
        return ""
    val = re.sub(r"<[^>]+>", " ", m.group(1) or "")
    val = re.sub(r"&nbsp;", " ", val, flags=re.I)
    val = re.sub(r"\s+", " ", val).strip().strip("：:|｜/\\")
    return val[:200]


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
    """子标题标签口径：film | resource（简繁/异写均认）。"""
    raw = scope[t_start:t_end] or ""
    m = re.search(r"【\s*([^】]+?)\s*】", raw)
    lab = re.sub(r"\s+", "", (m.group(1) if m else raw))
    if lab in RESOURCE_TITLE_FORMS:
        return "resource"
    if lab in FILM_TITLE_FORMS:
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


def extract_subresource_blocks(
    html: str,
    infohashes: list[str] | None = None,
    *,
    base_url: str = "",
    limit_per: int = 5,
    fallback_title: str = "",
) -> list[SubresourceBlock]:
    """按子标题切段：一段 = 一个子资源（段内多个磁力只取第一个）。

    规则：
    - 无子标题：整段主贴归帖标题，所有链同属这一条子资源
    - 1 个子标题：主贴内该标题下全部链同属它
    - ≥2 个子标题：第 i 个标题 → 下一个标题之前（最后一段到文尾）
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
            return []

    mag_pos = _magnet_positions_in_scope(scope, wanted)
    if wanted:
        # 只要还在 wanted 里的 hash（可能仅 ed2k）；无位置的稍后无法切段
        mag_pos = [x for x in mag_pos if x[0] in wanted]
    if not mag_pos:
        return []

    titles = iter_subresource_title_spans(scope)
    lim = max(1, int(limit_per or 5))
    out: list[SubresourceBlock] = []
    seen: set[str] = set()

    # 无子标题：整帖一段，标题用帖子标题
    if not titles:
        name = (fallback_title or "").strip()[:255]
        if not name:
            return []
        paired = mag_pos[0][0]
        raw_chunk = scope
        text_chunk = re.sub(r"<[^>]+>", " ", raw_chunk or "")
        text_chunk = re.sub(r"&nbsp;", " ", text_chunk, flags=re.I)
        size = _size_from_subresource_block(scope, 0, len(scope))
        size_label = _block_field(text_chunk, *SIZE_FIELD_FORMS)
        fmt = _block_field(text_chunk, *FORMAT_FIELD_FORMS)
        note = _block_field(text_chunk, *NOTE_FIELD_FORMS)
        torrent = _block_field(text_chunk, *TORRENT_FIELD_FORMS)
        imgs = extract_preview_images(raw_chunk, limit=lim, base_url=base_url)
        desc = _build_block_description(
            title=name, size_label=size_label, fmt=fmt, note=note, kind="film"
        )
        return [
            SubresourceBlock(
                infohash=paired,
                title=name,
                size=size,
                format=fmt,
                note=note,
                torrent_name=torrent,
                preview_images=imgs,
                description=desc,
            )
        ]

    layout = _detect_magnet_title_layout(titles, mag_pos)

    for i, (t_start, t_end) in enumerate(titles):
        next_start = titles[i + 1][0] if i + 1 < len(titles) else len(scope)
        prev_end = titles[i - 1][1] if i > 0 else 0
        name = _subresource_title_value(scope, t_end, next_start)
        if not name:
            continue

        # 字段区：本标题值之后 → 下一标题之前（最后到文尾）
        field_lo, field_hi = t_end, next_start
        # 磁力归属：
        # - 名称在前：本标题起 → 下一标题前
        # - 磁力在前：上一标题结束 → 本标题起（旧布局）
        if layout == "title_then_magnet":
            mag_lo, mag_hi = t_start, next_start
        else:
            mag_lo, mag_hi = prev_end, t_start

        in_seg = [
            (h, s, e) for h, s, e in mag_pos if mag_lo <= s < mag_hi and h not in seen
        ]
        if not in_seg:
            continue
        # 一段一个子资源：取段内第一个磁力
        paired = in_seg[0][0]
        seen.add(paired)

        raw_chunk = scope[field_lo:field_hi]
        text_chunk = re.sub(r"<[^>]+>", " ", raw_chunk or "")
        text_chunk = re.sub(r"&nbsp;", " ", text_chunk, flags=re.I)
        size = _size_from_subresource_block(scope, field_lo, field_hi)
        size_label = _block_field(text_chunk, *SIZE_FIELD_FORMS)
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
        imgs = extract_preview_images(raw_chunk, limit=lim, base_url=base_url)
        kind = _title_label_kind(scope, t_start, t_end)
        desc = _build_block_description(
            title=name,
            size_label=size_label,
            fmt=fmt,
            note=note,
            kind=kind,
        )
        out.append(
            SubresourceBlock(
                infohash=paired,
                title=name,
                size=size,
                format=fmt,
                note=note,
                torrent_name=torrent,
                preview_images=imgs,
                description=desc,
            )
        )
    return out


def _subresource_title_value(scope: str, label_end: int, next_start: int) -> str:
    """取【影片名称】/【资源名称】标签后的片名。"""
    chunk = scope[label_end:next_start]
    chunk = re.sub(r"<[^>]+>", " ", chunk or "")
    chunk = re.sub(r"&nbsp;", " ", chunk, flags=re.I)
    chunk = re.sub(r"\s+", " ", chunk).strip()
    m = _SUBRESOURCE_TITLE_VALUE_RE.match(chunk)
    if not m:
        return ""
    name = (m.group(1) or "").strip().strip("：:|｜/\\")
    return name[:255]


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
        preview_images=extract_preview_images(html, limit=5, base_url=base_url),
        extract_password=extract_password(combined, metadata),
    )
