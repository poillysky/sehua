"""Magnet link parsing (infohash / dn / xl)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from parsers.resource_names import context_subresource_title

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

_FILM_SIZE_RE = re.compile(
    r"【\s*(?:影片大小|影片容量|资源大小|資源大小|文件大小|檔案大小|档案大小)\s*】"
    r"\s*[:：]?\s*([0-9.]+)\s*(T|TB|G|GB|M|MB|K|KB)?",
    re.I,
)

# 中文编辑粘贴常见：全角标点 + 零宽/软连字符（防复制检测）
# 另：2048 国内原创常见【ＨＡＳＨ】全角拉丁（须折半角再认线索）
_FULLWIDTH_TRANS = str.maketrans(
    {
        "：": ":",
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

# 防和谐砍字母：agnet / magne / magent / mgnet
_CLIPPED_MAGNET_HEAD_RE = re.compile(
    rf"(?<![A-Za-z0-9])(?:agnet|magne|magent|mgnet)\s*:\s*\??\s*xt\s*=\s*urn\s*:\s*btih\s*:\s*"
    rf"({_INFOHASH})",
    re.I,
)

# btih 与 hash 之间用空格代替冒号
_BTIH_SPACE_HASH_RE = re.compile(
    rf"(magnet:\?xt=urn:btih)\s+({_INFOHASH})",
    re.I,
)

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
    for seed in ("种", "種"):
        for code in ("码", "碼"):
            labels.append(f"{seed}子特{code}")
        for back in _BARE_HASH_BACK2:
            labels.append(f"{seed}子{back}")
    labels.extend(("HASH", "Hash", "hash", "哈希"))
    return tuple(dict.fromkeys(labels))


_BARE_HASH_STRUCTURE_CUES = bare_infohash_structure_cue_labels()
_BARE_HASH_STRUCTURE_ALT = "|".join(re.escape(x) for x in _BARE_HASH_STRUCTURE_CUES)

# 线索与 hash 之间：空白/冒号/括号，以及 2048 实录「哈希校验; HASH; ;」（tid 27433099）
_BARE_HASH_GAP = (
    r"(?:"
    r"[\s:：\|\[\]【】=\-_;；,，\.．]"
    r"|哈希校验|哈希值|雜湊校[验驗]|哈希校[验驗]"
    r"|<[^>\n]{0,120}>"
    r"){0,80}"
)

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
    out = _ENTITY_COLON_RE.sub(":", out)
    out = _MAGNET_BTIH_TAG_JUNK_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
        out,
    )
    out = _MAGNET_BTIH_DATE_PREFIX_RE.sub(
        lambda m: f"{m.group(1)}{m.group(2)}",
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
    out = _expand_rmdown_hashes(out)
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
    if u in {"K", "KB"}:
        mult = 1024
    elif u in {"M", "MB"}:
        mult = 1024**2
    elif u in {"G", "GB"}:
        mult = 1024**3
    elif u in {"T", "TB"}:
        mult = 1024**4
    return int(val * mult)


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
            size = _size_from_label(sm.group(1), sm.group(2))
            break
    if not size and name:
        emb = re.search(
            r"\[\s*(?:MP4|MKV|AVI|WMV|MOV|FLV|TS|ISO)?\s*/\s*([0-9.]+)\s*([KMGT])B?\s*\]",
            name,
            re.I,
        )
        if emb:
            size = _size_from_label(emb.group(1), emb.group(2))
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

    for match in MAGNET_URI_RE.finditer(blob):
        parsed = _parse_magnet_uri(match.group(0))
        if not parsed or parsed.infohash in seen:
            continue
        ctx_name, ctx_size = _context_name_and_size(blob, match.start(), match.end())
        # 子资源名 = 帖内【影片名称】/【资源名称】，优先于 dn= 链内名
        if ctx_name:
            parsed = MagnetLink(
                infohash=parsed.infohash,
                filename=ctx_name[:255],
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
