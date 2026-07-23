"""资源命名：主资源 title=帖子标题；子资源=【影片名称】/【资源名称】，不是链内文件名。"""

from __future__ import annotations

import re

# 解析器对无 dn 磁力的占位名：magnet-A14DF085
_PLACEHOLDER_MAGNET_RE = re.compile(r"^magnet-[0-9A-Fa-f]{8}$", re.I)

# ---------------------------------------------------------------------------
# 真正「子资源标题 / 资源名」结构标签（子标题切分、上下文命名共用）
#
# 2026-07 对 resource_sources.description 抽样约 8 万条：
#   【影片名称】≈7.7万  【资源名称】≈0.27万
#   【种子名称】/【作品名称】/【片名】等结构键 = 0（不进 description）
#
# 板块口径：
#   BT 原创电影 → 影片名称
#   综合 95 / 网友原创 141 → 资源名称
#   转帖 142 → 资源名称 或 影片名称（二选一）
#
# 【种子名称】只是种子文件名，不是子标题，切段时绝不能当边界。
# 正文偶见繁体【影片名稱】/【資源名稱】，匹配时与简体等价。
# ---------------------------------------------------------------------------
SUBRESOURCE_TITLE_LABELS: tuple[str, ...] = ("影片名称", "资源名称")

# 匹配用（简繁）；顺序：影片类优先，再资源类；组内简体在前
SUBRESOURCE_TITLE_MATCH_FORMS: tuple[str, ...] = (
    "影片名称",
    "影片名稱",
    "资源名称",
    "資源名稱",
)

_SUBRESOURCE_NAME_RES = tuple(
    re.compile(
        rf"【\s*{re.escape(lab)}\s*】\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*ed2k:|\s*$)",
        re.I | re.S,
    )
    for lab in SUBRESOURCE_TITLE_MATCH_FORMS
)

# description 行式：【资源名称】value
_DESC_LABEL_LINE_RE = re.compile(
    r"^【\s*([^】]+)\s*】\s*[:：]?\s*(.+)$",
    re.M,
)

_TORRENT_NAME_RE = re.compile(
    r"【\s*(?:种子名称|種子名稱)\s*】\s*[:：]?\s*(.+?)(?=\s*【|\s*magnet:|\s*ed2k:|\s*$)",
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
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("：:|｜/\\")
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

    合集常见顺序是「链接 → 子标题」，故先后文再前文最近一条。
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
    """从结构化 description 取第一条【资源名称】/【影片名称】。"""
    text = (description or "").strip()
    if not text:
        return ""
    # 影片名称优先（与 SUBRESOURCE_TITLE_LABELS 一致）
    wanted = {
        "影片名称",
        "影片名稱",
        "资源名称",
        "資源名稱",
    }
    found: dict[str, str] = {}
    for m in _DESC_LABEL_LINE_RE.finditer(text):
        lab = (m.group(1) or "").strip()
        val = _clean_label_value(m.group(2) or "")
        if lab in wanted and val and lab not in found:
            found[lab] = val
    for lab in ("影片名称", "影片名稱", "资源名称", "資源名稱"):
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
