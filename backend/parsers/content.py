"""Structured fields and plain text from Discuz thread HTML."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

# BT + ED2K board label styles commonly used on sehuatang（2026-07 抽样核对）
LABEL_KEYS = (
    "影片名称",
    "资源名称",
    "出演女优",
    "影片容量",
    "影片大小",
    "资源大小",
    "文件大小",
    "影片格式",
    "资源类型",
    "资源数量",
    "是否有码",
    "有无码",
    "影片码别",
    "有无水印",
    "有无第三方水印",
    "解压密码",
    "提取密码",
    "种子期限",
    "下载方式",
    "下载工具",
    "时间长度",
    "影片有无声音",
    "剧情连拍截图/缩略图",
    "资源预览",
    "查重证明图",
    "前缀证明图",
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
    "影片格式": "资源类型",
    "文件大小": "资源大小",
    "影片容量": "资源大小",
    "影片大小": "资源大小",
    "有无码": "是否有码",
    "影片码别": "是否有码",
    "有无水印": "有无第三方水印",
    "提取密码": "解压密码",
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
            "有无码": "是否有码",
            "文件大小": "影片大小",
            "资源大小": "影片大小",
            "提取密码": "解压密码",
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
            "文件大小": "资源大小",
            "影片容量": "资源大小",
            "影片大小": "资源大小",
            "有无第三方水印": "有无水印",
            "有无码": "是否有码",
            "提取密码": "解压密码",
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
            "有无码": "是否有码",
            "提取密码": "解压密码",
        },
        "title_as": "资源名称",
    },
}


def description_profile_for_board(board_fid: str | int | None) -> dict:
    fid = str(board_fid or "").strip()
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
# 「解压密码是www.98T.la@」——「是/为」是系词不是密码；也兼容冒号/等号
PASSWORD_RE = re.compile(
    r"(?:解压|提取)\s*密码\s*(?:[:：=]|是|为)?\s*([^\s【】\n，,。；;]+)",
    re.I,
)
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


def _clip_field_value(value: str, *, password: bool = False) -> str:
    """裁掉粘在后面的【下一字段】及后续噪声。"""
    val = " ".join((value or "").replace("\r", "\n").split())
    val = val.lstrip(":：").strip()
    if not val:
        return ""
    m = _NEXT_FIELD_RE.search(val)
    if m:
        val = val[: m.start()].strip()
    if password:
        # 密码通常是单 token；后面若跟中文说明再硬切
        m2 = re.search(r"\s+[\u4e00-\u9fff]", val)
        if m2:
            val = val[: m2.start()].strip()
        if len(val) > 120:
            val = val[:120].strip()
    return val


def extract_metadata(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for m in LABEL_RE.finditer(text or ""):
        key = m.group(1).strip()
        is_pwd = key in {"解压密码", "提取密码"}
        val = _clip_field_value(m.group(2), password=is_pwd)
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
    for key in ("解压密码", "提取密码"):
        val = _clip_field_value(meta.get(key) or "", password=True)
        # 【解压密码】：是www.xxx → 剥掉行首系词
        if val.startswith(("是", "为")) and len(val) > 1:
            val = _clip_field_value(val[1:], password=True)
        if val and not _is_bogus_password(val):
            return val
    m = PASSWORD_RE.search(text or "")
    if not m:
        return ""
    val = _clip_field_value(m.group(1), password=True)
    return "" if _is_bogus_password(val) else val


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
        is_pwd = key == "解压密码"
        val = _clip_field_value(raw_val, password=is_pwd)
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


def extract_blockcode_text(html: str) -> str:
    parts: list[str] = []
    for m in BLOCKCODE_RE.finditer(html or ""):
        parts.append(_clean_text(m.group(1)))
    return "\n".join(parts)


def parse_thread_content(html: str, tid: int = 0, *, base_url: str = "") -> ThreadContent:
    """Build structured content from raw thread HTML (no link parsing)."""
    title = extract_title(html)
    plain = _clean_text(html)
    block = extract_blockcode_text(html)
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
