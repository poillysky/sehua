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
# 「影片名称代号」须写在「影片名称」前，避免短标签抢匹配（虽有】锚点，仍保持长优先）
FILM_TITLE_FORMS: tuple[str, ...] = (
    "影片名称代号",
    "影片名稱代號",
    "影片名称代號",
    "影片名稱代号",
    "名称代号",
    "名稱代號",
    "原文片名",  # 老含及无码破坏精选等
    "原影片名",
    "原片名称",
    "原片名稱",
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
    "套图名称",  # 套图写真合集
    "套圖名稱",
    "套图名稱",
    "套圖名称",
    "图片名称",
    "圖片名稱",
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
    "档案格式",
    "文件格式",
    "文件类型",  # FC2/合集常见粘在片名后
    "文件類型",
    "檔案類型",
    "档案类型",
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
# 标签与值之间的分隔符（半角/全角冒号、点号、竖线、间隔号等反爬符号）
_STRUCTURE_SEP = r"[:：︰﹒．.｜|/／·・•‧＝=\-_;；,，〜～﹕→]?"
# 标签字间反爬间隙（空格/间隔号/点号等）——仅用于少量局部兜底，勿拼进巨型 alt
_INTER_LABEL_GAP = (
    r"(?:[\s\u3000]|[·・•‧.．_\-﹣－/／|｜]|&nbsp;|&amp;nbsp;)*"
)

# 汉字间反爬空格/间隔号（禁止嵌套 +，否则长空白 ReDoS）
_CJK_INSERTED_SPACE_RE = re.compile(
    r"(?<=[\u4e00-\u9fff])"
    r"(?:"
    r"[\s\u3000·・•‧.．_\-﹣－/／|｜]"
    r"|&nbsp;|&amp;nbsp;"
    r"){1,64}"
    r"(?=[\u4e00-\u9fff])"
)


def collapse_cjk_inserted_spaces(text: str) -> str:
    """去掉汉字之间的反爬空格/nbsp/间隔号。"""
    if not text:
        return ""
    return _CJK_INSERTED_SPACE_RE.sub("", text)


# 兼容旧名
_collapse_cjk_inserted_spaces = collapse_cjk_inserted_spaces


def normalize_structure_label_key(label: str) -> str:
    """标签键：折叠字间空/间隔号并去空白。"""
    key = collapse_cjk_inserted_spaces((label or "").strip())
    return re.sub(r"\s+", "", key)


def collapse_structure_label_gaps(text: str) -> str:
    """只折叠结构括号内标签字间空，保留字段值里的「真·名」等间隔号。

    匹配前先跑一遍，即可用字面标签 alt，避免数千分支 flexible 正则。
    """
    if not text:
        return ""
    out = text
    for op, cl in STRUCTURE_BRACKET_PAIRS:
        pat = re.compile(
            re.escape(op)
            + r"([^"
            + re.escape(cl)
            + r"\n]{1,40})"
            + re.escape(cl)
        )

        def _repl(m: re.Match[str], _op: str = op, _cl: str = cl) -> str:
            return f"{_op}{normalize_structure_label_key(m.group(1))}{_cl}"

        out = pat.sub(_repl, out)
    return out


def structure_labels_alt(labels: tuple[str, ...] | list[str]) -> str:
    """字面标签交替（匹配前须已 collapse_structure_label_gaps / 标签已归一）。"""
    seen: set[str] = set()
    parts: list[str] = []
    for lab in labels:
        key = normalize_structure_label_key(lab)
        if not key or key in seen:
            continue
        seen.add(key)
        parts.append(re.escape(key))
    # 长标签优先，避免「影片名称」被「影片名」抢前缀（字面 | 无该问题，但仍按长度稳妥）
    parts.sort(key=len, reverse=True)
    return "|".join(parts)


def flexible_structure_label_re(label: str) -> str:
    """（遗留）字间可插空的单标签片段。新代码请用 collapse + structure_labels_alt。"""
    chars = [c for c in (label or "") if not c.isspace()]
    if not chars:
        return ""
    if any("\u4e00" <= c <= "\u9fff" for c in chars):
        return _INTER_LABEL_GAP.join(re.escape(c) for c in chars)
    return re.escape("".join(chars))

# 片名取值截断边界：仅「已知结构字段」，勿在装饰性【S级泄密】【自转】等处切断
EXTRA_STRUCTURE_BOUNDARY_FORMS: tuple[str, ...] = (
    "出演女优",
    "出演女優",
    "有无水印",
    "有無浮水印",
    "是否有水印",  # 2048 独家合集常见
    "是否有浮水印",
    "有无第三方水印",
    "有無第三方浮水印",
    "第三方水印",
    "第三方浮水印",
    "目录树",  # 独家帖结构尾巴，勿吞进片名
    "目錄樹",
    "资源大小/数量",
    "資源大小/數量",
    "资源大小／数量",
    "資源大小／數量",
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
    "做种期限",
    "做種期限",
    "下载方式",
    "下載方式",
    "下载工具",
    "下載工具",
    "下载软件",
    "下載軟件",
    "下載軟體",
    "清晰程度",
    "预览图片",
    "預覽圖片",
    "预览圖片",
    "預覽图片",
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
    "磁力连接",  # 2048 合集常见简体「连接」
    "磁力連接",
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
    "注意事项",  # 套图合集常见解压提示
    "注意事項",
    "资源介绍",
    "資源介紹",
    "资源介紹",
    "資源介绍",
    "剧情介绍",
    "劇情介紹",
    "剧情簡介",
    "剧情简介",
    "外文名",
    "外 文 名",
    "类 型",
    "類 型",
    "上映时间",
    "上映時間",
    "制片地区",
    "製片地區",
    "片 长",
    "片 長",
    "导 演",
    "導 演",
    "主 演",
    "编剧",
    "編劇",
    "主演女優",
    "主演女优",
    "カテゴリで探す",
    "カテゴリ",
    "シリーズ",
    "スタジオ",
    # 老含及等：【验証码】= infohash（証），勿与站内「验证码」混淆但须作字段边界
    "验証码",
    "驗証碼",
    "验証碼",
    "驗証码",
    "校验码",
    "校驗碼",
    "校验碼",
    "校驗码",
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

# 结构字段开闭括号对（识别帖面用哪套，再按「下一开括号=新标签」切）
STRUCTURE_BRACKET_PAIRS: tuple[tuple[str, str], ...] = (
    ("【", "】"),
    ("［", "］"),
    ("〖", "〗"),
    ("「", "」"),
    ("『", "』"),
    ("[", "]"),
)

# 标签后常见分隔：冒号/等号/竖线等才像结构字段。
# 勿含中英文逗号——片名装饰「??【新流】，正文…」会被误切成只剩 ??（tid=26644722）
# 勿含下划线——「64【海砂原创】_玩弄…」会被误切成 64（tid=24592539）
_STRUCTURE_LABEL_SEP_CLASS = r"[:：︰﹒．.｜|/／·・•‧＝=\-;；〜～﹕→]"


def detect_structure_bracket_pair(text: str | None) -> tuple[str, str]:
    """从文本统计「开+短标签+闭+分隔」最常见的一对；默认【】。"""
    blob = text or ""
    best: tuple[str, str] = ("【", "】")
    best_n = 0
    for op, cl in STRUCTURE_BRACKET_PAIRS:
        pat = re.compile(
            re.escape(op)
            + r"[^"
            + re.escape(cl)
            + r"\n]{1,40}"
            + re.escape(cl)
            + r"\s*"
            + _STRUCTURE_LABEL_SEP_CLASS
        )
        n = len(pat.findall(blob))
        if n > best_n:
            best_n = n
            best = (op, cl)
    return best


def _bracket_inner_class(close: str) -> str:
    """闭括号字符类转义（用于 [^】\\n]）。"""
    return re.escape(close)


def any_structure_bracket_label_re() -> re.Pattern[str]:
    """任意已知括号对的「开…闭」标签（不问标签名）——非片名字段遇此即截。"""
    alts = "|".join(
        re.escape(op)
        + r"[^"
        + _bracket_inner_class(cl)
        + r"\n]{1,40}"
        + re.escape(cl)
        for op, cl in STRUCTURE_BRACKET_PAIRS
    )
    return re.compile(rf"\s*(?:{alts})")


def labeled_structure_field_re() -> re.Pattern[str]:
    """「开…闭」后跟分隔符的结构标签（不问标签名）——片名/文件名用，避免装饰【合集】误切。"""
    alts = "|".join(
        re.escape(op)
        + r"[^"
        + _bracket_inner_class(cl)
        + r"\n]{1,40}"
        + re.escape(cl)
        for op, cl in STRUCTURE_BRACKET_PAIRS
    )
    return re.compile(rf"\s*(?:{alts})\s*{_STRUCTURE_LABEL_SEP_CLASS}")


_ANY_STRUCTURE_BRACKET_LABEL_RE = any_structure_bracket_label_re()
_LABELED_STRUCTURE_FIELD_RE = labeled_structure_field_re()

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

_STRUCTURE_BOUNDARY_ALT = structure_labels_alt(STRUCTURE_FIELD_BOUNDARY_FORMS)
# 片名可含嵌套装饰括号 / ??※★ 等前缀；只裁到下一已知结构字段 / 磁力 / ed2k
_TITLE_VALUE_TAIL = (
    rf"(?=\s*{STRUCTURE_FIELD_OPEN}\s*(?:{_STRUCTURE_BOUNDARY_ALT})\s*{STRUCTURE_FIELD_CLOSE}"
    rf"|\s*magnet:|\s*ed2k:|\s*$)"
)

_SUBRESOURCE_TITLE_ALT = structure_labels_alt(SUBRESOURCE_TITLE_MATCH_FORMS)
_SUBRESOURCE_NAME_RES = tuple(
    re.compile(
        rf"{STRUCTURE_FIELD_OPEN}\s*{re.escape(normalize_structure_label_key(lab))}\s*{STRUCTURE_FIELD_CLOSE}"
        rf"\s*{_STRUCTURE_SEP}\s*(.+?){_TITLE_VALUE_TAIL}",
        re.I | re.S,
    )
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS
    if normalize_structure_label_key(lab)
)

# description 行式：【资源名称】value（亦认异写括号）
_DESC_LABEL_LINE_RE = re.compile(
    rf"^{STRUCTURE_FIELD_OPEN}\s*([^】］〗」』\]]+)\s*{STRUCTURE_FIELD_CLOSE}"
    rf"\s*{_STRUCTURE_SEP}\s*(.+)$",
    re.M,
)

_TORRENT_NAME_ALT = structure_labels_alt(TORRENT_FIELD_FORMS)
_TORRENT_NAME_RE = re.compile(
    rf"{STRUCTURE_FIELD_OPEN}\s*(?:"
    + _TORRENT_NAME_ALT
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


# 仅装饰：emoji / 心形 / 星号 / 问号占位（【影片名称】：❤️）——无实质片名
_DECORATION_ONLY_RE = re.compile(
    r"^[\s"
    r"\U0001F300-\U0001FAFF"  # emoji
    r"\u2600-\u27BF"  # misc symbols
    r"\uFE0E\uFE0F\u200D"  # VS / ZWJ
    r"❤♥♡❥❣️⭐★☆✦✧✩✪✫✬✭✮✯✰＊※●○◆◇■□▲△▼▽☀☁☂♠♣♪♫♀♂㊣"
    r"\?？!！~～·•‧。.、，,;；:：\-—__=+|/／\\|]"
    r"+$"
)


def is_decoration_only_filename(filename: str | None) -> bool:
    """整段只有装饰符/emoji/问号，没有中文或目录号实质。"""
    n = (filename or "").strip()
    if not n:
        return True
    if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", n):
        return False
    return bool(_DECORATION_ONLY_RE.fullmatch(n))


def is_acceptable_short_title(text: str | None) -> bool:
    """短片名是否可保留：1～3 字中文、短目录号（OM1），勿因 len<4 误杀。"""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if is_hard_dirty_filename(t) or is_dirty_filename(t):
        return False
    if is_decoration_only_filename(t):
        return False
    if len(t) >= 4:
        return True
    # 1～3：含中文即可（「甲」「油鬼子」）
    if re.search(r"[\u4e00-\u9fff]", t):
        return True
    # 2～3：拉丁目录号
    if len(t) >= 2 and re.fullmatch(r"[A-Za-z]{1,8}\d{0,4}[A-Za-z]?", t):
        return True
    return False


def salvage_short_subresource_name(raw: str | None) -> str:
    """clip 过空时抢救短中文/目录号（切块漏名的高发点）。"""
    # 先取首行，再去 markup（sanitize 会把换行压成空格）
    text = (raw or "").strip().split("\n", 1)[0].strip()
    text = sanitize_filename_markup(text)
    text = re.sub(r"^[:：﹒．.|｜/\\]+", "", text)
    text = re.sub(r"[:：﹒．.|｜/\\]+$", "", text).strip()
    text = text.strip(" ，,、·•|-")
    if is_acceptable_short_title(text):
        return text[:FILENAME_SOFT_MAX]
    return ""


def is_collection_album_header(name: str | None) -> bool:
    """合集专辑头，不是子资源真名。

    - ★★最强優片★★…專輯…[日期]
    - ★◇精彩の…精品合集…♀[日期]
    """
    n = re.sub(r"\s+", "", (name or "").strip())
    if not n:
        return False
    if re.match(r"^★*最强優片★*.*專輯.*\[\d[\d.]*\]$", n):
        return True
    if re.match(r"^★◇精彩の.+精品合集.+♀\[[\d.]+\]$", n):
        return True
    return False


def is_weak_subresource_name(
    name: str | None,
    *,
    post_title: str = "",
    hash_value: str = "",
) -> bool:
    """弱名：空/占位/回落帖标题/过短垃圾 —— 多资源上视为切块未认出真名。"""
    if is_missing_filename(name, hash_value=hash_value):
        return True
    n = (name or "").strip()
    t = (post_title or "").strip()
    if t and n == t:
        return True
    # 空格差异仍视作帖标题（如 [12.27 ] vs [12.27]）
    if t and re.sub(r"\s+", "", n) == re.sub(r"\s+", "", t):
        return True
    # 合集专辑头当子名（tid=23486061：subject 被改成单片名，首条仍写专辑头）
    if is_collection_album_header(n):
        return True
    if len(n) < 1:
        return True
    if is_decoration_only_filename(n):
        return True
    # 短串：无中文且非目录号 → 弱（如单字母 "A"）
    if len(n) < 4 and not is_acceptable_short_title(n):
        return True
    return False


def _clean_label_value(raw: str) -> str:
    """清洗标签值；保留片名常见装饰前缀（?? ※ ★ ！！ 等）。"""
    text = sanitize_filename_markup(raw or "")
    # 只剥字段分隔符，勿动 ?？!！*＊ 等装饰
    text = re.sub(r"^[:：﹒．.|｜/\\]+", "", text)
    text = re.sub(r"[:：﹒．.|｜/\\]+$", "", text)
    return text.strip()


def sanitize_filename_markup(raw: str | None) -> str:
    """去掉 HTML / BBCode / CF 邮件壳，压空白。"""
    import html as html_lib

    text = html_lib.unescape((raw or "").strip())
    if not text:
        return ""
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    # Discuz / 论坛常见 BBCode
    text = re.sub(r"\[/?url[^\]]*\]", " ", text, flags=re.I)
    text = re.sub(r"\[/?backcolor[^\]]*\]", " ", text, flags=re.I)
    text = re.sub(r"\[/?color[^\]]*\]", " ", text, flags=re.I)
    text = re.sub(r"\[/?b\]|\[/?i\]|\[/?u\]", " ", text, flags=re.I)
    text = re.sub(r"&nbsp;", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# HTML / BBCode：整段不可信（勿只裁尾留下前缀）
_HARD_DIRTY_FILENAME_RE = re.compile(
    r"(?is)"
    r"("
    r"<[^>]+>"
    r"|</?a\b"
    r"|target\s*=\s*[\"']?_blank"
    r"|data-cfemail"
    r"|cdn-cgi/l/email-protection"
    r"|__cf_email__"
    r"|\[/?url"
    r"|\[/?backcolor"
    r"|htmlspecialchars\s*\("
    r"|innerHTML\s*="
    r")"
)

# 论坛附件区 UI 粘进片名（判定丢弃 + clip 裁尾共用）
_FILENAME_ATTACH_UI_RE = re.compile(
    r"(?is)"
    r"("
    r"\.(?:gif|jpe?g|png|webp|bmp)\s*\([^)]{0,40}(?:MB|KB|GB)"
    r"|下载次数\s*:"
    r"|下載次數\s*:"
    r"|下载附件"
    r"|下載附件"
    r"|\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+上传"
    r")"
)

# 可裁尾的「资源介绍」—— dirty 但不 hard（clip 后可保留片名）
_SOFT_DIRTY_INTRO_RE = re.compile(r"【\s*资源介绍\s*】|【\s*資源介紹\s*】")

# 日文贩卖页元数据尾巴（须像字段标签：前空白 + 冒号），勿误伤 [スタジオVG] 等片名前缀
_FILENAME_JP_META_TAIL_RE = re.compile(
    r"(?:"
    r"(?:^|[\s　])(?:主演女優|主演女优|スタジオ|シリーズ)\s*[:：]"
    r"|カテゴリで探す"
    r"|カテゴリ\s*:"
    r")"
)

FILENAME_SOFT_MAX = 200


def is_hard_dirty_filename(filename: str | None) -> bool:
    """整段应丢弃的脏名（HTML/BBCode/附件 UI），不可裁尾保留前缀。"""
    text = (filename or "").strip()
    if not text:
        return False
    return bool(
        _HARD_DIRTY_FILENAME_RE.search(text) or _FILENAME_ATTACH_UI_RE.search(text)
    )


def is_dirty_filename(filename: str | None) -> bool:
    """脏名：hard，或粘了【资源介绍】（可先 clip 再判）。"""
    text = (filename or "").strip()
    if not text:
        return False
    if is_hard_dirty_filename(text):
        return True
    return bool(_SOFT_DIRTY_INTRO_RE.search(text))


def pick_subresource_title(window: str, *, prefer_last: bool) -> str:
    """从窗口取真正子标题值；优先名称角色卡片，再回落历史标签表。"""
    if not window:
        return ""
    from parsers.structure_cards import name_values_from_cards, parse_structure_cards

    names = name_values_from_cards(parse_structure_cards(window))
    if names:
        name = names[-1] if prefer_last else names[0]
        name = _clean_label_value(name)
        if name:
            return name
    text = collapse_structure_label_gaps(window)
    for cre in _SUBRESOURCE_NAME_RES:
        hits = list(cre.finditer(text))
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
        before_n = collapse_structure_label_gaps(before)
        for m in _TORRENT_NAME_RE.finditer(before_n):
            torr = m
        if torr:
            name = _clean_label_value(torr.group(1))
            # 与 content._torrent_name_as_title 对齐：去 .torrent / 尾部「 torrent」
            name = re.sub(r"(?i)(?:\.torrent|\s+torrent)\s*$", "", name or "").strip()
    if name:
        name = clip_subresource_display_name(name)
        if is_dirty_filename(name):
            return ""
    return name or ""


def subtitle_from_description(description: str | None) -> str:
    """从结构化 description 取子名：影片类标签优先于资源类（2048 双名互斥另议）。"""
    text = (description or "").strip()
    if not text:
        return ""
    from parsers.structure_cards import parse_structure_cards

    cards = parse_structure_cards(text)
    by_lab = {
        c.raw_label: (c.value or "").strip()
        for c in cards
        if c.role == "name" and (c.value or "").strip()
    }
    if by_lab:
        res_key = normalize_structure_label_key("资源名称")
        film_key = normalize_structure_label_key("影片名称")
        res = by_lab.get(res_key)
        film = by_lab.get(film_key)
        if res and film and film != res and (
            film.startswith("2048") or (res in film and len(res) + 4 <= len(film))
        ):
            return res
        for lab in SUBRESOURCE_TITLE_MATCH_FORMS:
            key = normalize_structure_label_key(lab)
            if key in by_lab:
                return by_lab[key]
        # 其它名称角色（作品名称等已在 MATCH_FORMS；兜底任意 name）
        return next(iter(by_lab.values()))

    text = collapse_structure_label_gaps(text)
    wanted = {normalize_structure_label_key(x) for x in SUBRESOURCE_TITLE_MATCH_FORMS}
    found: dict[str, str] = {}
    for m in _DESC_LABEL_LINE_RE.finditer(text):
        lab = normalize_structure_label_key(m.group(1) or "")
        val = _clean_label_value(m.group(2) or "")
        if lab in wanted and val and lab not in found:
            found[lab] = val
    res_key = normalize_structure_label_key("资源名称")
    film_key = normalize_structure_label_key("影片名称")
    if res_key in found and film_key in found:
        film = found[film_key]
        res = found[res_key]
        if res and film != res and (
            film.startswith("2048") or (res in film and len(res) + 4 <= len(film))
        ):
            return res
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS:
        key = normalize_structure_label_key(lab)
        if key in found:
            return found[key]
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
    """子资源名：【影片名称】/【资源名称】→ 主资源标题；绝不用 ed2k/dn 链内名。

    弱名（=帖标题 / 仅装饰 emoji / 过短）不得抢在 description 真名之前；
    帖标题仅作最后回落（单资源常见）。
    """
    main = (title or "").strip()
    link_name = filename_from_link(link_uri)
    link_norm = link_name.strip().lower()

    def _is_link_tech_filename(name: str) -> bool:
        """链内技术文件名（alone.mp4 / www.98T.la@x.mp4），不是展示片名。"""
        t = (name or "").strip()
        if not t:
            return False
        low = t.lower()
        if re.search(
            r"\.(?:mp4|mkv|avi|wmv|mov|flv|ts|m4v|rmvb|iso|rar|zip|7z|txt)(?:$|[\s\|./])",
            low,
        ):
            return True
        if low.startswith("www.98") or "98t.la@" in low:
            return True
        return False

    def _usable(cand: str | None, *, allow_title: bool = False) -> str:
        text = (cand or "").strip()
        if not text or is_missing_filename(text, hash_value=hash_value):
            return ""
        # 与链内技术名相同 → 不是子资源名；片名碰巧等于 magnet dn 时仍可用
        if (
            link_norm
            and text.lower() == link_norm
            and _is_link_tech_filename(text)
        ):
            return ""
        # HTML / 附件 UI：整段丢弃，避免留下 gif hash 前缀
        if is_hard_dirty_filename(text):
            return ""
        text = _clip_filename_structure_tail(text)
        if not text or is_dirty_filename(text) or is_hard_dirty_filename(text):
            return ""
        if is_missing_filename(text, hash_value=hash_value):
            return ""
        # 弱名（含 =帖标题、仅❤️/??）跳过，让 description 真名有机会上位
        if not allow_title and is_weak_subresource_name(
            text, post_title=main, hash_value=hash_value
        ):
            return ""
        return text

    for cand in (
        inner_name,
        subtitle_from_description(description),
    ):
        got = _usable(cand, allow_title=False)
        if got:
            return got[:FILENAME_SOFT_MAX]
    if main:
        clipped = _usable(main, allow_title=True)
        if clipped:
            return clipped[:FILENAME_SOFT_MAX]
        soft = sanitize_filename_markup(main)
        soft = _clip_filename_structure_tail(soft)
        if soft and not is_dirty_filename(soft) and not is_decoration_only_filename(soft):
            return soft[:FILENAME_SOFT_MAX]
    h = (hash_value or "").strip() or "resource"
    return h[:FILENAME_SOFT_MAX]


_FILENAME_BUY_TIP_RE = re.compile(r"购买本帖|預覽圖\s*:|预览图\s*:")
# 港台修复版常见：片名后直接跟「导演: … 主演: …」元数据
_FILENAME_CREDIT_TAIL_RE = re.compile(
    r"\s+(?:"
    r"导演|導演|编剧|編劇|主演|演员|演員|"
    r"类型|類型|制片国家/?地区|製片國家/?地區|制片国家|製片國家|"
    r"语言|語言|片长|片長|上映日期|又名"
    r")\s*[:：]"
)
_FILENAME_LEADING_DASH_RE = re.compile(r"^[\-\u2013\u2014\s]{1,}")
# [MP4/1.5G] -真名 / 【MP4/4.39G】：码 等容量装饰，勿当「开括号+分隔」结构字段
_MEDIA_CAPACITY_IN_BRACKETS_RE = re.compile(
    r"(?i)(?:MP4|AVI|MKV|WMV|MOV|FLV|TS|M4V|RMVB|ISO)\s*/\s*[\d.,]+\s*[KMGT]?B?"
)


def _is_media_capacity_labeled_field(matched: str) -> bool:
    """片名容量前缀（如 [MP4/1.5G] -）不是结构字段，裁掉会清空整名。"""
    return bool(_MEDIA_CAPACITY_IN_BRACKETS_RE.search(matched or ""))


def clip_subresource_display_name(text: str | None) -> str:
    """公开入口：清洗子资源展示名（结构尾巴 / 演职员元数据 / 前导破折号）。"""
    import re

    raw = (text or "").strip()
    if not raw:
        return ""
    # 入库前再剥一次残缺 HTML（切块偶发漏网）
    raw = re.sub(r"<[^>]*>", " ", raw)
    raw = re.sub(r"</?[A-Za-z][^<\n]*", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return _clip_filename_structure_tail(raw)


# 国产原创常见：把结构字段整段塞进帖标题
# 「B 【影片名称】：真名 【出演女优】：…」（tid=1475266）→ 真名
# 「【影片名称】：真名」（tid=2156323）→ 真名
_SUBJECT_NAME_LABEL_RE = re.compile(
    rf"{STRUCTURE_FIELD_OPEN}\s*"
    rf"(?:影片名称|影片名稱|资源名称|資源名稱|影片名|视频名称|視頻名稱|作品名称|作品名稱)"
    rf"\s*{STRUCTURE_FIELD_CLOSE}\s*{_STRUCTURE_SEP}\s*",
    re.I,
)
_SUBJECT_BOARD_LETTER_RE = re.compile(
    rf"^[A-Za-z]\s+(?={STRUCTURE_FIELD_OPEN}\s*"
    rf"(?:影片名称|影片名稱|资源名称|資源名稱|影片名))"
)


def unwrap_subject_film_title(title: str | None) -> str:
    """帖标题内嵌【影片名称】/【资源名称】时还原为片名。

    正文常不再重复写片名；若原样入库会把前缀 ``B`` 裁成资源名，或整段带标签污染。
    无此类标签时原样返回（不去掉无关的前导字母）。
    """
    t = " ".join((title or "").split()).strip()
    if not t:
        return ""
    if not _SUBJECT_NAME_LABEL_RE.search(t):
        return t
    t = _SUBJECT_BOARD_LETTER_RE.sub("", t).strip()
    m = _SUBJECT_NAME_LABEL_RE.search(t)
    if not m:
        return t
    val = t[m.end() :].strip()
    # 剥嵌套「【影片名称】：【影片名称】：真名」
    while True:
        m2 = _SUBJECT_NAME_LABEL_RE.match(val)
        if not m2:
            break
        val = val[m2.end() :].strip()
    val = _clip_filename_structure_tail(val)
    val = re.sub(r"\s*【\s*\.\.\.\s*】?\s*$", "", val).strip()
    val = re.sub(r"\s*\.\.\.\s*$", "", val).strip()
    if val and len(val) >= 2:
        return val
    return t


def _soft_truncate_filename(val: str, *, limit: int = FILENAME_SOFT_MAX) -> str:
    """超长时在空格/】处回退截断，避免硬切到 255。"""
    text = (val or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("】", "）", ")", " ", "　", "/", "／", "-", "·"):
        idx = cut.rfind(sep)
        if idx >= max(40, limit // 3):
            return cut[: idx + (1 if sep in {"】", "）", ")"} else 0)].strip()
    return cut.strip()


def _clip_filename_structure_tail(text: str | None) -> str:
    """去掉片名后粘连的结构字段 / 购买提示 / 影讯元数据（长度顶到上限前先语义截断）。

    下一字段按结构卡片开标签切（角色 stem 或「开闭+分隔」），不依赖边界白名单。
    """
    from parsers.structure_cards import find_next_structure_field_start

    val = sanitize_filename_markup(text)
    if not val:
        return ""
    val = _FILENAME_LEADING_DASH_RE.sub("", val).strip()
    val = collapse_structure_label_gaps(val)
    cut_at = find_next_structure_field_start(val, min_start=1)
    if cut_at is not None and cut_at > 0:
        kept = val[:cut_at].strip()
        # 裁空则放弃本次截断，避免回落帖标题（tid=22924760）
        if kept:
            val = kept
    m2 = _FILENAME_BUY_TIP_RE.search(val)
    if m2:
        val = val[: m2.start()].strip()
    m3 = _FILENAME_CREDIT_TAIL_RE.search(val)
    if m3:
        val = val[: m3.start()].strip()
    m4 = _FILENAME_ATTACH_UI_RE.search(val)
    if m4:
        val = val[: m4.start()].strip()
    m5 = _FILENAME_JP_META_TAIL_RE.search(val)
    if m5:
        val = val[: m5.start()].strip()
    val = re.sub(r"\s+", " ", val).strip()
    return _soft_truncate_filename(val)
