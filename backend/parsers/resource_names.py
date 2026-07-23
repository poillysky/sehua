"""资源命名：主资源 title=帖子标题；子资源 filename=有名用自己的，无名用标题。"""

from __future__ import annotations

import re

from parsers.ed2k import parse_ed2k_text

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


def filename_from_link(uri: str | None) -> str:
    """从 ed2k URI 抽文件名；磁力无 dn 则空。"""
    raw = (uri or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("ed2k://"):
        parsed = parse_ed2k_text(raw)
        if parsed and parsed[0].filename:
            return parsed[0].filename.strip()
    if "dn=" in raw.lower():
        # 简易抽 dn（完整解析走 magnet 模块更稳，这里够用）
        from urllib.parse import unquote
        from parsers.magnet import parse_magnet_text

        mags = parse_magnet_text(raw)
        if mags and mags[0].filename and not is_missing_filename(
            mags[0].filename, hash_value=mags[0].infohash
        ):
            return mags[0].filename.strip()
        # dn 存在但被当成占位时仍尝试 query
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
) -> str:
    """子资源名：有真实文件名用自己的，否则用主资源标题，再否则 hash。"""
    main = (title or "").strip()
    candidates = [
        (inner_name or "").strip(),
        filename_from_link(link_uri),
    ]
    for cand in candidates:
        if cand and not is_missing_filename(cand, hash_value=hash_value):
            return cand[:255]
    if main:
        return main[:255]
    h = (hash_value or "").strip() or "resource"
    return h[:255]
