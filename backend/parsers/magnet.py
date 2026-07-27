"""Magnet link parsing (infohash / dn / xl)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from parsers.resource_names import (
    collapse_cjk_inserted_spaces as _collapse_cjk_inserted_spaces,
    context_subresource_title,
)

# BT infohash：40 位 hex（SHA1）/ 32 位 hex（转帖常见短链，如 tid 2758065）/ 32 位 base32
_INFOHASH = r"(?:[A-Fa-f0-9]{40}|[A-Fa-f0-9]{32}|[a-zA-Z2-7]{32})"

MAGNET_URI_RE = re.compile(
    rf"magnet:\?xt=urn:btih:{_INFOHASH}(?:&[^\s<>\"'\]【】]{{1,200}}){{0,12}}",
    re.I,
)
BTIH_RE = re.compile(
    rf"xt=urn:btih:({_INFOHASH})",
    re.I,
)

DN_RE = re.compile(r"(?:^|&)dn=([^&]+)", re.I)
XL_RE = re.compile(r"(?:^|&)xl=(\d+)", re.I)

# 字段值可能是「13V 66.7GB」「635V/1.3TB」「2.6G/1V」——整段交给 parse_capacity_bytes
# 语料经 normalize_magnet_corpus 已折叠汉字间空，标签用字面匹配
def _film_size_label_alt() -> str:
    from parsers.resource_names import SIZE_FIELD_FORMS, structure_labels_alt

    return structure_labels_alt(SIZE_FIELD_FORMS)


_FILM_SIZE_RE = re.compile(
    rf"【\s*(?:{_film_size_label_alt()})\s*】"
    r"\s*[:：︰｜|/／·・•‧＝=\-_;；,，〜～﹕→]?\s*([^\n【]{1,96})",
    re.I,
)

# 容量数字+单位（排除前面的 13V 片数）
_CAPACITY_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])([0-9]+(?:\.[0-9]+)?)\s*"
    r"(TB|TIB|GB|GIB|MB|MIB|KB|KIB|T|G|M|K)(?![A-Za-z])",
    re.I,
)

# 中文编辑粘贴常见：全角标点 + 零宽/软连字符（防复制检测）
# 另：2048 国内原创常见【ＨＡＳＨ】全角拉丁（须折半角再认线索）
_FULLWIDTH_TRANS = str.maketrans(
    {
        "：": ":",
        "︰": ":",  # U+FE30 竖排冒号（色花堂结构字段常用，如 tid 1537403）
        "？": "?",
        "＆": "&",
        "＝": "=",
        "／": "/",
        "．": ".",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
        "\u00ad": "",
        **{chr(0xFF21 + i): chr(ord("A") + i) for i in range(26)},
        **{chr(0xFF41 + i): chr(ord("a") + i) for i in range(26)},
        **{chr(0xFF10 + i): chr(ord("0") + i) for i in range(10)},
    }
)

# HTML 实体冒号（blockcode 偶发）
_ENTITY_COLON_RE = re.compile(r"&colon;|&#0*58;|&#x0*3a;", re.I)

# m a g n e t : ? xt = urn : btih : HASH（协议头被空格拆开；字母间至少一处空格，避免误伤正常 magnet）
_SPACED_MAGNET_SCHEME_RE = re.compile(
    rf"(?<![A-Za-z0-9])m\s+a\s+g\s+n\s+e\s+t\s*:\s*\??\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# magnet : ? xt = urn : btih : HASH（半角被空格打断）
_SPACED_MAGNET_CORE_RE = re.compile(
    rf"magnet\s*:\s*\?\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# 发帖/附件防和谐：去掉冒号；亦覆盖 urn/btih/hash 间缺冒号
_COLONLESS_MAGNET_RE = re.compile(
    rf"magnet\s*\??\s*xt\s*=\s*urn\s*:?\s*btih\s*:?\s*"
    rf"({_INFOHASH})",
    re.I,
)

# 缺 ?：magnet:xt=… / magnet:/?xt= / magnet://?xt=
_MAGNET_NO_QMARK_RE = re.compile(
    rf"magnet\s*:\s*(?:/+)?\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# 防和谐砍字母：agnet / magne / magent / mgnet / net（magnet 残成 net:?；tid 582630）
_CLIPPED_MAGNET_HEAD_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:agnet|magne|magent|mgnet|net)\s*:\s*\??\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# btih 与 hash 之间用空格代替冒号
_BTIH_SPACE_HASH_RE = re.compile(
    rf"(magnet:\?xt=urn:btih)\s+({_INFOHASH})",
    re.I,
)

# hash 被顿号/逗号/点号/换行/br 打断（tid 1540160；tid 191451 用 <br> 拆 40 位）
_MAGNET_BTIH_SPLIT_HASH_RE = re.compile(
    rf"(magnet:\?xt=urn:btih:)"
    rf"((?:[A-Fa-f0-9]{{2,}}"
    rf"(?:[\s、，,．.\u00b7·]|&nbsp;|&amp;nbsp;|<br\s*/?>)*"
    rf"){{1,12}}[A-Fa-f0-9]{{2,}})",
    re.I,
)


def _stitch_split_btih_hash(m: re.Match[str]) -> str:
    chunk = m.group(2) or ""
    # 先去掉 br/nbsp，避免 <br> 里的字母 b/a/f 混进 hex
    chunk = re.sub(r"<br\s*/?>", "", chunk, flags=re.I)
    chunk = re.sub(r"&nbsp;|&amp;nbsp;", "", chunk, flags=re.I)
    hex_only = re.sub(r"[^A-Fa-f0-9]", "", chunk)
    if len(hex_only) in (32, 40):
        return f"{m.group(1)}{hex_only}"
    return m.group(0)

# Discuz「复制代码」旁裸 infohash（例：复制代码下载：f7809dc8…）
# 转帖常见【哈希校验】：40位 hex（tid 3628517）
#
# 「特征/验证/试证」×「编码/编号/全码/码」简繁组合（帖内实录）：
#   特征*：可短写「特征码」；2048 常见「特征全码」
#   验证*：必须「验证编号/验证编码/验证全码」，禁止「验证码」（会误伤站内验证码文案）
#   试证*：帖内错别字（特→试），与特征*同后缀；如「试证全码」与资源大小同行（tid 27431995）
# 另：「种子特码」结构不同，单独匹配。
#
# 禁止用裸「磁力」「BT」作线索：标题【BT/磁力】在大 HTML 上会触发灾难性回溯卡死进程。
# 间隔必须有上限，禁止 (?:…)*? 扫整页。
_BARE_HASH_FRONT_FEATURE = tuple(f"特{c}" for c in ("征", "徵"))
_BARE_HASH_FRONT_VERIFY = tuple(
    a + b for a in ("验", "驗") for b in ("证", "證", "証")
)
_BARE_HASH_FRONT_SHIZHENG = tuple(
    a + b for a in ("试", "試") for b in ("证", "證", "証")
)
_BARE_HASH_BACK2 = tuple(
    c + d for c in ("编", "編") for d in ("号", "號", "码", "碼")
)
_BARE_HASH_BACK_FULL = ("全码", "全碼")
_BARE_HASH_BACK1_FEATURE = ("码", "碼")  # 仅特征*/试证*短写；禁止验证码


def bare_infohash_structure_cue_labels() -> tuple[str, ...]:
    """结构标签芯片对应的裸 hash 线索（与 regex / 组合测试同源）。"""
    labels: list[str] = []
    for front in _BARE_HASH_FRONT_FEATURE:
        for back in (*_BARE_HASH_BACK2, *_BARE_HASH_BACK_FULL, *_BARE_HASH_BACK1_FEATURE):
            labels.append(front + back)
    for front in _BARE_HASH_FRONT_VERIFY:
        for back in (*_BARE_HASH_BACK2, *_BARE_HASH_BACK_FULL):
            labels.append(front + back)
    for front in _BARE_HASH_FRONT_SHIZHENG:
        for back in (*_BARE_HASH_BACK2, *_BARE_HASH_BACK_FULL, *_BARE_HASH_BACK1_FEATURE):
            labels.append(front + back)
    # 老含及【验証码】（証）：infohash 短标签；勿加「验证码」（易撞站内验证码文案）
    labels.extend(("验証码", "驗証碼", "验証碼", "驗証码", "校验码", "校驗碼"))
    for seed in ("种", "種"):
        for code in ("码", "碼"):
            labels.append(f"{seed}子特{code}")
        for back in _BARE_HASH_BACK2:
            labels.append(f"{seed}子{back}")
    labels.extend(("HASH", "Hash", "hash", "哈希"))
    # 色花堂「磁力链接」帖常见：【下载地址】后直接跟 40 位 infohash（无 magnet: 前缀）
    labels.extend(
        (
            "下载地址",
            "下載地址",
            "下载链接",
            "下載鏈接",
            "下载连接",
            "下載連接",
            "下载連结",
            "下載連结",
        )
    )
    return tuple(dict.fromkeys(labels))


_BARE_HASH_STRUCTURE_CUES = bare_infohash_structure_cue_labels()

# 线索与 hash 之间：空白/冒号/括号/竖线/间隔号等（tid 718959 &nbsp;；竖排冒号︰）
_BARE_HASH_GAP = (
    r"(?:"
    r"[\s:：︰\|｜/／\[\]【】=\＝\-_;；,，\.．·・•‧〜～﹕→]"
    r"|哈希校验|哈希值|雜湊校[验驗]|哈希校[验驗]"
    r"|&nbsp;|&amp;nbsp;"
    r"|<[^>\n]{0,120}>"
    r"){0,80}"
)

# 色花反爬空格折叠：parsers.resource_names.collapse_cjk_inserted_spaces


def _bare_hash_structure_alt() -> str:
    from parsers.resource_names import structure_labels_alt

    return structure_labels_alt(_BARE_HASH_STRUCTURE_CUES)


_BARE_HASH_STRUCTURE_ALT = _bare_hash_structure_alt()

_BARE_INFOHASH_CUED_RE = re.compile(
    r"(?:"
    r"复制代码(?:下载)?"
    r"|哈希校验"
    r"|哈希值"
    r"|雜湊校[验驗]"
    r"|哈希校[验驗]"
    r"|磁力(?:链接|连接|鍊接|連結)"
    r"|BT\s*(?:哈希|hash)"
    r"|info\s*hash"
    r"|种子(?:哈希|hash)"
    r"|種子(?:哈希|hash)"
    # 2048 国内原创：【HASH】/【ＨＡＳＨ】(全角拉丁先折半角)
    r"|HASH"
    r"|哈希"
    rf"|{_BARE_HASH_STRUCTURE_ALT}"
    r")"
    rf"{_BARE_HASH_GAP}"
    rf"({_INFOHASH})"
    r"(?![A-Fa-f0-9])",
    re.I,
)

# rmdown.com/link.php?hash=26{40hex}（前缀常为 26；与种子特码同值）
_RMDOWN_HASH_RE = re.compile(
    r"(?:https?://)?(?:www\.)?rmdown\.com/link\.php\?hash="
    r"(?:[0-9a-f]{1,4})?([A-Fa-f0-9]{40})",
    re.I,
)

# 更宽：任意 */torrent/{40hex}（downsx 等镜像；色花堂旧合集常见无 magnet 正文）
_TORRENT_PATH_HASH_GENERIC_RE = re.compile(
    r"(?:https?://)[^\s\"'<>]*/torrent/([A-Fa-f0-9]{40})",
    re.I,
)

# blockcode 里把 hash 包进转义/真实标签
_MAGNET_BTIH_TAG_JUNK_RE = re.compile(
    rf"(magnet:\?xt=urn:btih:)"
    rf"(?:(?:<[^>\n]{{0,200}}>)|(?:&lt;(?:(?!&gt;).){{0,200}}&gt;)|\s)*"
    rf"({_INFOHASH})"
    rf"(?:(?:</[^>\n]{{0,80}}>)|(?:&lt;/(?:(?!&gt;).){{0,80}}&gt;)|\s)*",
    re.I,
)

# magnet:?xt=urn:btih:202601/HASH（tid 3286293）
_MAGNET_BTIH_DATE_PREFIX_RE = re.compile(
    rf"(magnet:\?xt=urn:btih:)(?:[0-9]{{4,8}}/)+({_INFOHASH})",
    re.I,
)

# magnet:?xt=urn:btih:/HASH（误插斜杠；tid 700913 / 707141）
_MAGNET_BTIH_LEADING_SLASH_RE = re.compile(
    rf"(magnet:\?xt=urn:btih:)/+({_INFOHASH})",
    re.I,
)

# magnet:?xt=urn:HASH（缺 btih:；tid 442964）
_MAGNET_URN_MISSING_BTIH_RE = re.compile(
    rf"(magnet:\?xt=urn:)(?!btih:)({_INFOHASH})",
    re.I,
)

# magnet:?xt=urn:btih:link.aspx?hash=HEX（jukujo 等站点把 hash 包进伪下载页；tid 1256892）
_MAGNET_BTIH_LINK_ASPX_RE = re.compile(
    rf"(magnet:\?xt=urn:btih:)link\.aspx\?hash=({_INFOHASH})",
    re.I,
)

# magnet:? 与 xt=urn:btih: 被 font/br/blockcode 拆开（tid 2012676）
_MAGNET_SPLIT_SCHEME_XT_RE = re.compile(
    rf"magnet\s*:\s*\?"
    rf"(?:(?:</?(?:font|div|span|br|li|ol|ul|p|em|strong|b|i)\b[^>\n]*>)"
    rf"|&nbsp;|&amp;nbsp;|\s){{0,80}}"
    rf"(?:<(?:div|ol|ul|li)\b[^>\n]*>\s*){{0,6}}"
    rf"xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# magnet:?dn=NAME&xt=urn:btih:HASH（dn 在 xt 前；JAVPLAYER tid 513815）
_MAGNET_XT_AFTER_PARAMS_RE = re.compile(
    rf"magnet:\?"
    rf"(?:(?!xt=)[^&\s<>\"'#]+&(?:amp;)?)+"
    rf"xt=urn:btih:({_INFOHASH})",
    re.I,
)


def _expand_rmdown_hashes(text: str) -> str:
    """rmdown 下载页 hash 参数 → magnet（与正文种子特码同值时去重由后续逻辑处理）。"""
    if not text or "rmdown.com" not in text.lower():
        return text or ""

    known = {m.group(1).lower() for m in BTIH_RE.finditer(text)}

    def repl(m: re.Match[str]) -> str:
        h = m.group(1)
        key = h.lower()
        if key in known:
            return m.group(0)
        known.add(key)
        return f"{m.group(0)} magnet:?xt=urn:btih:{h} "

    return _RMDOWN_HASH_RE.sub(repl, text)


def _expand_torrent_path_hashes(text: str) -> str:
    """downsx 等 /torrent/{infohash} 下载页 → 追加 magnet，便于统一解析。"""
    if not text or "/torrent/" not in text.lower():
        return text or ""

    known = {m.group(1).lower() for m in BTIH_RE.finditer(text)}

    def repl(m: re.Match[str]) -> str:
        h = m.group(1)
        key = h.lower()
        if key in known:
            return m.group(0)
        known.add(key)
        return f"{m.group(0)} magnet:?xt=urn:btih:{h} "

    # 先走 generic，覆盖 downsX 及其它镜像
    return _TORRENT_PATH_HASH_GENERIC_RE.sub(repl, text)


def _expand_bare_infohashes(text: str) -> str:
    """把带提示语的裸 infohash 原地换成 magnet:?xt=urn:btih:…，便于后续统一解析。"""
    if not text:
        return ""
    known = {m.group(1).lower() for m in BTIH_RE.finditer(text)}

    def repl(m: re.Match[str]) -> str:
        h = m.group(1)
        before = text[max(0, m.start(1) - 32) : m.start(1)].lower()
        if "btih:" in before or "magnet:?" in before:
            return m.group(0)
        key = h.lower()
        if key in known:
            return m.group(0)
        known.add(key)
        head = m.group(0)[: m.start(1) - m.start()]
        tail = m.group(0)[m.end(1) - m.start() :]
        return f"{head}magnet:?xt=urn:btih:{h} {tail}"

    return _BARE_INFOHASH_CUED_RE.sub(repl, text)


def normalize_magnet_corpus(text: str) -> str:
    """把全角标点 / 被空格拆开 / 去冒号防和谐 / 标签打断 / 裸 infohash 还原成标准形式。"""
    if not text:
        return ""
    out = text.translate(_FULLWIDTH_TRANS)
    out = _collapse_cjk_inserted_spaces(out)
    out = _ENTITY_COLON_RE.sub(":", out)
    out = _MAGNET_BTIH_TAG_JUNK_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
        out,
    )
    out = _MAGNET_BTIH_DATE_PREFIX_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
        out,
    )
    out = _MAGNET_BTIH_LEADING_SLASH_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
        out,
    )
    out = _MAGNET_URN_MISSING_BTIH_RE.sub(
        lambda m: f"{m.group(1)}btih:{m.group(2)}",
        out,
    )
    out = _MAGNET_BTIH_LINK_ASPX_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
        out,
    )
    out = _MAGNET_SPLIT_SCHEME_XT_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _MAGNET_XT_AFTER_PARAMS_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _SPACED_MAGNET_SCHEME_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _SPACED_MAGNET_CORE_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _MAGNET_NO_QMARK_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _COLONLESS_MAGNET_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _CLIPPED_MAGNET_HEAD_RE.sub(
        lambda m: f"magnet:?xt=urn:btih:{m.group(1)}",
        out,
    )
    out = _BTIH_SPACE_HASH_RE.sub(
        lambda m: f"{m.group(1)}:{m.group(2)}",
        out,
    )
    out = _MAGNET_BTIH_SPLIT_HASH_RE.sub(_stitch_split_btih_hash, out)
    out = _expand_rmdown_hashes(out)
    out = _expand_torrent_path_hashes(out)
    out = _expand_bare_infohashes(out)
    return out


@dataclass(slots=True)
class MagnetLink:
    infohash: str
    filename: str
    size: int
    link: str


def _normalize_infohash(raw: str) -> str:
    return unquote(raw.strip()).upper()


def _size_from_label(raw_num: str, unit: str | None) -> int:
    try:
        val = float(raw_num)
    except (TypeError, ValueError):
        return 0
    u = (unit or "M").upper()
    mult = 1
    if u in {"K", "KB", "KIB"}:
        mult = 1024
    elif u in {"M", "MB", "MIB"}:
        mult = 1024**2
    elif u in {"G", "GB", "GIB"}:
        mult = 1024**3
    elif u in {"T", "TB", "TIB"}:
        mult = 1024**4
    return int(val * mult)


def parse_capacity_bytes(text: str | None) -> int:
    """从「13V 66.7GB」「635V/1.3TB」「2.6G/1V」「【989V/1.5T】」等文本取容量字节。

    忽略纯片数（数字+V）；同段多个容量单位时取最大字节值。
    """
    raw = (text or "").strip()
    if not raw:
        return 0
    # 先走结构化【资源大小】字段
    sm = _FILM_SIZE_RE.search(raw)
    if sm:
        got = parse_capacity_bytes(sm.group(1))
        if got:
            return got
    best = 0
    for m in _CAPACITY_TOKEN_RE.finditer(raw):
        # 紧贴在 NNNV 后的数字仍要认（13V 66.7GB）；token 本身不会匹配 V
        n = _size_from_label(m.group(1), m.group(2))
        if n > best:
            best = n
    if best:
        return best
    emb = re.search(
        r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
        raw,
        re.I,
    )
    if emb:
        return _size_from_label(emb.group(1), emb.group(2))
    return 0


def _context_name_and_size(blob: str, start: int, end: int) -> tuple[str, int]:
    """子资源名只认【影片名称】/【资源名称】；尺寸与片名同侧就近取。"""
    name = context_subresource_title(
        blob, start, end, allow_torrent_fallback=True
    )
    before = re.sub(r"<[^>]+>", " ", blob[max(0, start - 800) : start])
    after = re.sub(r"<[^>]+>", " ", blob[end : end + 480])
    size = 0
    # 与命名一致：先后文再前文，避免吃到上一条的【影片大小】
    for window in (after, before):
        sm = _FILM_SIZE_RE.search(window)
        if sm:
            size = parse_capacity_bytes(sm.group(1))
            break
    if not size and name:
        size = parse_capacity_bytes(name)
    return name, size


def _parse_magnet_uri(uri: str) -> MagnetLink | None:
    match = BTIH_RE.search(uri)
    if not match:
        return None

    infohash = _normalize_infohash(match.group(1))
    if not infohash:
        return None

    query = uri.split("?", 1)[-1]
    filename = ""
    dn_match = DN_RE.search(query)
    if dn_match:
        filename = unquote(dn_match.group(1).replace("+", " ")).strip()

    size = 0
    xl_match = XL_RE.search(query)
    if xl_match:
        size = int(xl_match.group(1))

    if not filename:
        filename = f"magnet-{infohash[:8]}"

    return MagnetLink(infohash=infohash, filename=filename, size=size, link=uri)


def parse_magnet_text(text: str) -> list[MagnetLink]:
    results: list[MagnetLink] = []
    seen: set[str] = set()
    blob = normalize_magnet_corpus(text or "")

    matches = list(MAGNET_URI_RE.finditer(blob))
    # 附件大包/纯链清单：无结构片名时跳过逐链上下文取名（900+ 链可省大半解析时间）
    skip_context = len(matches) >= 48 and not re.search(
        r"【\s*(?:影片|资源|資源|种子|種子)\s*名称",
        blob,
    )

    for match in matches:
        parsed = _parse_magnet_uri(match.group(0))
        if not parsed or parsed.infohash in seen:
            continue
        if not skip_context:
            ctx_name, ctx_size = _context_name_and_size(blob, match.start(), match.end())
            # 子资源名 = 帖内【影片名称】/【资源名称】，优先于 dn= 链内名
            if ctx_name:
                from parsers.resource_names import clip_subresource_display_name

                clean_name = clip_subresource_display_name(ctx_name) or ctx_name
                parsed = MagnetLink(
                    infohash=parsed.infohash,
                    filename=clean_name[:255],
                    size=parsed.size or ctx_size,
                    link=parsed.link,
                )
            elif ctx_size and not parsed.size:
                parsed = MagnetLink(
                    infohash=parsed.infohash,
                    filename=parsed.filename,
                    size=ctx_size,
                    link=parsed.link,
                )
        seen.add(parsed.infohash)
        results.append(parsed)

    return results


def pick_primary_magnet(links: list[MagnetLink]) -> MagnetLink | None:
    if not links:
        return None
    sized = [link for link in links if link.size > 0]
    if sized:
        return max(sized, key=lambda item: item.size)
    return links[0]


def has_abnormal_download_link(text: str) -> bool:
    """结构标签 / 半截 magnet / 残缺 ed2k 后出现非法长度 hash → 异常下载链接。

    合法：infohash 32/40 hex；ed2k MD4 恰好 32 hex。
    例：tid 3027518 【特徵全碼】仅 31 位 hex。
    """
    raw = text or ""
    if not raw or not re.search(r"[A-Fa-f0-9]{20,}", raw):
        return False
    blob = normalize_magnet_corpus(raw)
    # magnet:?xt=urn:btih: + 非 32/40 的 hex 串
    for m in re.finditer(
        r"magnet:\s*\?\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*([A-Fa-f0-9]{8,64})",
        blob,
        re.I,
    ):
        if len(m.group(1)) not in (32, 40):
            return True
    # 【特征全码】等线索后的近合法但长度不对的 hex
    for m in re.finditer(
        rf"(?:{_BARE_HASH_STRUCTURE_ALT})"
        rf"{_BARE_HASH_GAP}"
        rf"([A-Fa-f0-9]{{20,64}})"
        r"(?![A-Fa-f0-9])",
        blob,
        re.I,
    ):
        if len(m.group(1)) not in (32, 40):
            return True
    # ed2k 链 hash 非 32
    for m in re.finditer(
        r"ed2k://\|file\|[^|\n]{1,400}\|\d+\|([A-Fa-f0-9]+)\|",
        blob,
        re.I,
    ):
        if len(m.group(1)) != 32:
            return True
    return False
