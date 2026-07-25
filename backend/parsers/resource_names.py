"""资源命名：主资源 title=帖子标题；子资源=【影片名称】/【资源名称】，不是链内文件名。"""

from __future__ import annotations

import re

# 解析器对无 dn 磁力的占位名：magnet-A14DF085
_PLACEHOLDER_MAGNET_RE = re.compile(r"^magnet-[0-9A-Fa-f]{8}$", re.I)

# ---------------------------------------------------------------------------
# 真正「子资源标题 / 资源名」结构标签（子标题切分、上下文命名共用）
#
# 板块口径：
#   BT 原创电影 → 影片名称
#   综合 95 / 网友原创 141 → 资源名称
#   转帖 142 → 资源名称 或 影片名称（二选一）
#
# 【种子名称】只是种子文件名，不是子标题，切段时绝不能当边界。
# 简繁及常见异写均认；匹配时与规范键等价。
# ---------------------------------------------------------------------------
SUBRESOURCE_TITLE_LABELS: tuple[str, ...] = ("影片名称", "资源名称")

# 影片类子标题（简繁/异写）；优先于资源类
FILM_TITLE_FORMS: tuple[str, ...] = (
    "影片名称",
    "影片名稱",
    "影片名",
    "影片标题",
    "影片標題",
    "影片题名",
    "影片題名",
    "视频名称",
    "視頻名稱",
    "视频名稱",
    "視頻名称",
)

# 资源类子标题（简繁/异写）
RESOURCE_TITLE_FORMS: tuple[str, ...] = (
    "资源名称",
    "資源名稱",
    "资源名稱",
    "資源名称",
    "资源名",
    "資源名",
    "资源标题",
    "資源標題",
    "资源標題",
    "資源标题",
    "作品名称",
    "作品名稱",
    "片名",
)

# 匹配用：影片类优先，再资源类；组内简体/常见写在前
SUBRESOURCE_TITLE_MATCH_FORMS: tuple[str, ...] = FILM_TITLE_FORMS + RESOURCE_TITLE_FORMS

# 块内字段异写（取字段值时用；不含子标题）
SIZE_FIELD_FORMS: tuple[str, ...] = (
    "影片大小",
    "影片容量",
    "资源大小",
    "資源大小",
    "文件大小",
    "檔案大小",
    "档案大小",
)
FORMAT_FIELD_FORMS: tuple[str, ...] = (
    "影片格式",
    "资源类型",
    "資源類型",
    "资源類型",
    "資源类型",
    "檔案格式",
    "文件格式",
)
NOTE_FIELD_FORMS: tuple[str, ...] = (
    "影片说明",
    "影片說明",
    "资源说明",
    "資源說明",
    "资源說明",
    "資源说明",
    "是否有码",
    "是否有碼",
    "有无码",
    "有無碼",
    "影片码别",
    "影片碼別",
)
TORRENT_FIELD_FORMS: tuple[str, ...] = (
    "种子名称",
    "種子名稱",
    "种子名稱",
    "種子名称",
)

# 结构字段括号（帖内常见全角/半角异写）
STRUCTURE_FIELD_OPEN = r"[【［〖「『\[]"
STRUCTURE_FIELD_CLOSE = r"[】］〗」』\]]"
# 标签与值之间的分隔符（半角/全角冒号、点号）
_STRUCTURE_SEP = r"[:：﹒．.]?"

# 片名取值截断边界：仅「已知结构字段」，勿在装饰性【S级泄密】【自转】等处切断
EXTRA_STRUCTURE_BOUNDARY_FORMS: tuple[str, ...] = (
    "出演女优",
    "出演女優",
    "有无水印",
    "有無浮水印",
    "有无第三方水印",
    "有無第三方浮水印",
    "第三方水印",
    "第三方浮水印",
    "解压密码",
    "解壓密碼",
    "解压码",
    "解壓碼",
    "提取密码",
    "提取密碼",
    "提取码",
    "提取碼",
    "资源密码",
    "資源密碼",
    "资源码",
    "資源碼",
    "种子期限",
    "種子期限",
    "作种期限",
    "作種期限",
    "下载方式",
    "下載方式",
    "下载工具",
    "下載工具",
    "时间长度",
    "時間長度",
    "影片时间",
    "影片時間",
    "影片时长",
    "影片時長",
    "影片有无声音",
    "影片有無聲音",
    "影片截图",
    "影片截圖",
    "影片预览",
    "影片預覽",
    "图片预览",
    "圖片預覽",
    "中文片名",
    "特征全码",
    "特徵全碼",
    "特征编码",
    "特徵編碼",
    "特征编号",
    "特徵編號",
    "特征码",
    "特徵碼",
    # 帖内错别字：试证 ≈ 特征/验证（常与资源大小同行）
    "试证全码",
    "試證全碼",
    "试证编码",
    "試證編碼",
    "试证编号",
    "試證編號",
    "试证码",
    "試證碼",
    "验证全码",
    "驗證全码",
    "驗證全碼",
    "验证编码",
    "驗證編碼",
    "验证编号",
    "驗證編號",
    "种子特码",
    "種子特碼",
    "种子编码",
    "種子編碼",
    "种子编号",
    "種子編號",
    "哈希校验",
    "哈希校驗",
    "哈希值",
    "雜湊校驗",
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
    "资源数量",
    "資源數量",
    "发布时间",
    "發布時間",
    "分辨率",
    "解析度",
    "磁力链接",
    "磁力連結",
    "迅雷链接",
    "迅雷連結",
    "电驴链接",
    "電驢連結",
    "网盘链接",
    "網盤連結",
    "分享链接",
    "分享連結",
    "提取码",
    "提取碼",
    "访问码",
    "訪問碼",
    "有效期",
    "码别",
    "碼別",
    "字幕",
    "音轨",
    "音軌",
    "画质",
    "畫質",
    "来源",
    "來源",
)

STRUCTURE_FIELD_BOUNDARY_FORMS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *SUBRESOURCE_TITLE_MATCH_FORMS,
            *SIZE_FIELD_FORMS,
            *FORMAT_FIELD_FORMS,
            *NOTE_FIELD_FORMS,
            *TORRENT_FIELD_FORMS,
            *EXTRA_STRUCTURE_BOUNDARY_FORMS,
        )
    )
)

_STRUCTURE_BOUNDARY_ALT = "|".join(
    map(re.escape, STRUCTURE_FIELD_BOUNDARY_FORMS)
)
# 片名可含嵌套装饰括号 / ??※★ 等前缀；只裁到下一已知结构字段 / 磁力 / ed2k
_TITLE_VALUE_TAIL = (
    rf"(?=\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_STRUCTURE_BOUNDARY_ALT})\s*{STRUCTURE_FIELD_CLOSE}"
    rf"|\s*magnet:|\s*ed2k:|\s*$)"
)

_SUBRESOURCE_NAME_RES = tuple(
    re.compile(
        rf"{STRUCTURE_FIELD_OPEN}\s*{re.escape(lab)}\s*{STRUCTURE_FIELD_CLOSE}"
        rf"\s*{_STRUCTURE_SEP}\s*(.+?){_TITLE_VALUE_TAIL}",
        re.I | re.S,
    )
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS
)

# description 行式：【资源名称】value（亦认异写括号）
_DESC_LABEL_LINE_RE = re.compile(
    rf"^{STRUCTURE_FIELD_OPEN}\s*([^】］〗」』\]]+)\s*{STRUCTURE_FIELD_CLOSE}"
    rf"\s*{_STRUCTURE_SEP}\s*(.+)$",
    re.M,
)

_TORRENT_NAME_RE = re.compile(
    rf"{STRUCTURE_FIELD_OPEN}\s*(?:"
    + "|".join(map(re.escape, TORRENT_FIELD_FORMS))
    + rf")\s*{STRUCTURE_FIELD_CLOSE}\s*{_STRUCTURE_SEP}\s*(.+?){_TITLE_VALUE_TAIL}",
    re.I | re.S,
)


def is_missing_filename(filename: str | None, *, hash_value: str = "") -> bool:
    """无有效文件名：空、磁力占位、或等于 hash。"""
    name = (filename or "").strip()
    if not name:
        return True
    h = (hash_value or "").strip().upper()
    if h and name.upper() == h:
        return True
    if h and len(h) >= 8 and name.upper() == h[:8]:
        return True
    if _PLACEHOLDER_MAGNET_RE.match(name):
        return True
    return False


def _clean_label_value(raw: str) -> str:
    """清洗标签值；保留片名常见装饰前缀（?? ※ ★ ！！ 等）。"""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    # 只剥字段分隔符，勿动 ?？!！*＊ 等装饰
    text = re.sub(r"^[:：﹒．.|｜/\\]+", "", text)
    text = re.sub(r"[:：﹒．.|｜/\\]+$", "", text)
    return text.strip()


def pick_subresource_title(window: str, *, prefer_last: bool) -> str:
    """从窗口取真正子标题值；标签优先级见 SUBRESOURCE_TITLE_LABELS。"""
    if not window:
        return ""
    for cre in _SUBRESOURCE_NAME_RES:
        hits = list(cre.finditer(window))
        if not hits:
            continue
        m = hits[-1] if prefer_last else hits[0]
        name = _clean_label_value(m.group(1))
        if name:
            return name
    return ""


def context_subresource_title(
    blob: str,
    start: int,
    end: int,
    *,
    allow_torrent_fallback: bool = False,
) -> str:
    """链接旁子资源名：只认【影片名称】/【资源名称】。

    单链就近：先后文再前文。多链合集由 pair_magnet_to_subresource_meta 按布局重绑。
    """
    before = (blob or "")[max(0, start - 280) : start]
    after = (blob or "")[end : end + 480]
    before = re.sub(r"<[^>]+>", " ", before)
    after = re.sub(r"<[^>]+>", " ", after)

    name = pick_subresource_title(after, prefer_last=False)
    if not name:
        name = pick_subresource_title(before, prefer_last=True)
    if not name and allow_torrent_fallback:
        torr = None
        for m in _TORRENT_NAME_RE.finditer(before):
            torr = m
        if torr:
            name = _clean_label_value(torr.group(1))
    return name


def subtitle_from_description(description: str | None) -> str:
    """从结构化 description 取第一条【资源名称】/【影片名称】（含繁体异写）。"""
    text = (description or "").strip()
    if not text:
        return ""
    wanted = set(SUBRESOURCE_TITLE_MATCH_FORMS)
    found: dict[str, str] = {}
    for m in _DESC_LABEL_LINE_RE.finditer(text):
        lab = (m.group(1) or "").strip()
        val = _clean_label_value(m.group(2) or "")
        if lab in wanted and val and lab not in found:
            found[lab] = val
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS:
        if lab in found:
            return found[lab]
    return ""


def filename_from_link(uri: str | None) -> str:
    """从 ed2k URI / magnet dn= 抽链内文件名（技术名，不是子资源名）。"""
    raw = (uri or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("ed2k://"):
        m = re.search(r"ed2k://\|file\|([^|]+)\|", raw, re.I)
        if m:
            return m.group(1).strip()
        return ""
    if "dn=" in raw.lower():
        from urllib.parse import unquote

        m = re.search(r"[?&]dn=([^&]+)", raw, re.I)
        if m:
            return unquote(m.group(1).replace("+", " ")).strip()
    return ""


def resolve_sub_filename(
    *,
    inner_name: str | None,
    title: str | None,
    hash_value: str = "",
    link_uri: str = "",
    description: str = "",
) -> str:
    """子资源名：【影片名称】/【资源名称】→ 主资源标题；绝不用 ed2k/dn 链内名。"""
    main = (title or "").strip()
    link_name = filename_from_link(link_uri)
    link_norm = link_name.strip().lower()

    def _usable(cand: str | None) -> str:
        text = (cand or "").strip()
        if not text or is_missing_filename(text, hash_value=hash_value):
            return ""
        # 与链内技术名相同 → 不是子资源名
        if link_norm and text.lower() == link_norm:
            return ""
        return text

    for cand in (
        inner_name,
        subtitle_from_description(description),
    ):
        got = _usable(cand)
        if got:
            return got[:255]
    if main:
        return main[:255]
    h = (hash_value or "").strip() or "resource"
    return h[:255]
