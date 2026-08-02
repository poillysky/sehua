# -*- coding: utf-8 -*-
"""结构字段：先按【标签】切卡片，再按角色归类。

人一眼扫帖：短括号标签开新卡；值先吃到下一卡，再按换行区分
「过长折行（软）」vs「字段结束/营销另起（硬）」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from parsers.resource_names import (
    STRUCTURE_BRACKET_PAIRS,
    collapse_structure_label_gaps,
    normalize_structure_label_key,
)

StructureRole = Literal[
    "name",
    "size",
    "type",
    "coded",
    "preview",
    "password",
    "torrent",
    "other",
]

# 标签后分隔（与 resource_names 片名裁切口径对齐；不含逗号/下划线）
_FIELD_SEP_CLASS = r"[:：︰﹒．.｜|/／·・•‧＝=\-;；〜～﹕→]"
_FIELD_SEP_RE = re.compile(rf"^\s*{_FIELD_SEP_CLASS}")

# [MP4/1.5G] 类容量装饰，不当结构字段
_MEDIA_CAPACITY_IN_BRACKETS_RE = re.compile(
    r"(?i)(?:MP4|AVI|MKV|WMV|MOV|FLV|TS|M4V|RMVB|ISO)\s*/\s*[\d.,]+\s*[KMGT]?B?"
)

_MAX_LABEL_LEN = 12

# 角色判定顺序：含「名称」的种子名须先于 name
_ROLE_RULES: tuple[tuple[StructureRole, tuple[str, ...]], ...] = (
    (
        "torrent",
        ("种子名称", "種子名稱", "种子名稱", "種子名称"),
    ),
    (
        "password",
        ("密码", "密碼", "解压码", "解壓碼", "提取码", "提取碼", "钥匙", "鑰匙"),
    ),
    (
        "preview",
        ("预览", "預覽", "截图", "截圖"),
    ),
    (
        "size",
        ("大小", "容量"),
    ),
    (
        "type",
        ("类型", "類型", "格式"),
    ),
    (
        "coded",
        (),  # 见 classify_structure_role 专用规则，避免「高清無碼」装饰误判
    ),
    (
        "name",
        (
            "名称",
            "名稱",
            "片名",
            "标题",
            "標題",
            "套图",
            "套圖",
            "影片名",
            "视频名",
            "視頻名",
            "资源名",
            "資源名",
            "作品名",
        ),
    ),
)

# 绝不当 name（即使标签含「名称」字样的边角）
_NAME_BLOCK_STEMS = (
    "种子",
    "種子",
    "特征",
    "特徵",
    "验证",
    "驗證",
    "验証",
    "驗証",
    "校验",
    "校驗",
    "试证",
    "試證",
    "哈希",
    "雜湊",
)

_HASH_LABEL_STEMS = (
    "特征",
    "特徵",
    "验证",
    "驗證",
    "验証",
    "驗証",
    "校验",
    "校驗",
    "试证",
    "試證",
    "哈希",
    "雜湊",
)

# 预编译：各括号对上的「开 + 短标签 + 闭」
_LABEL_FINDERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(
        re.escape(op)
        + r"([^"
        + re.escape(cl)
        + r"\n]{1,"
        + str(_MAX_LABEL_LEN)
        + r"})"
        + re.escape(cl)
    )
    for op, cl in STRUCTURE_BRACKET_PAIRS
)


@dataclass(frozen=True)
class StructureCard:
    raw_label: str
    role: StructureRole
    value: str
    start: int
    end: int
    label_end: int


_CODED_EXACT = frozenset(
    {
        "有码",
        "无码",
        "有碼",
        "無碼",
        "是否有码",
        "是否有碼",
        "有无码",
        "有無碼",
        "有无水印",
        "有無水印",
        "有无浮水印",
        "有無浮水印",
        "是否有水印",
        "是否有浮水印",
        "有无第三方水印",
        "有無第三方浮水印",
        "第三方水印",
        "第三方浮水印",
        "码别",
        "碼別",
        "影片码别",
        "影片碼別",
    }
)
_CODED_HINT = ("是否", "有无", "有無", "水印", "浮水印", "码别", "碼別")


def classify_structure_role(label: str) -> StructureRole:
    """按标签 stem 归角色（简繁已由 normalize 折叠字间空）。"""
    lab = normalize_structure_label_key(label)
    if not lab:
        return "other"
    # 精确种子名
    for exact in _ROLE_RULES[0][1]:
        if lab == normalize_structure_label_key(exact):
            return "torrent"
    if any(s in lab for s in ("种子名称", "種子名稱", "种子名稱", "種子名称")):
        return "torrent"
    if ("种子" in lab or "種子" in lab) and ("名称" in lab or "名稱" in lab):
        return "torrent"

    # 有码/水印：仅状态字段，勿把「高清無碼」装饰当字段
    if lab in _CODED_EXACT:
        return "coded"
    if any(h in lab for h in _CODED_HINT) and any(
        x in lab for x in ("码", "碼", "水印", "浮水印")
    ):
        return "coded"

    for role, stems in _ROLE_RULES[1:]:
        if role == "coded" or not stems:
            continue
        if role == "name" and any(b in lab for b in _NAME_BLOCK_STEMS):
            continue
        if any(s in lab for s in stems):
            return role
    return "other"


def is_hash_structure_label(label: str) -> bool:
    lab = normalize_structure_label_key(label)
    return bool(lab) and any(s in lab for s in _HASH_LABEL_STEMS)


def _remainder_has_sep(text: str, pos: int) -> bool:
    return bool(_FIELD_SEP_RE.match(text[pos:] if pos < len(text) else ""))


def _at_line_start(text: str, start: int) -> bool:
    if start <= 0:
        return True
    i = start - 1
    while i >= 0 and text[i] in " \t\u3000":
        i -= 1
    return i < 0 or text[i] == "\n"


def _line_value_preview(text: str, label_end: int) -> str:
    """标签后到本行末的取值预览（去可选分隔）。"""
    rest = text[label_end:] if label_end < len(text) else ""
    line = rest.split("\n", 1)[0]
    return _FIELD_SEP_RE.sub("", line, count=1).strip()


def is_structure_field_opener(
    label: str,
    text: str,
    label_end: int,
    *,
    matched: str = "",
    start: int = 0,
) -> bool:
    """是否应开一张结构卡片（不问是否在历史白名单）。"""
    lab = normalize_structure_label_key(label)
    if not lab or len(lab) > _MAX_LABEL_LEN:
        return False
    blob = matched or ""
    if _MEDIA_CAPACITY_IN_BRACKETS_RE.search(blob):
        return False
    role = classify_structure_role(lab)
    if role != "other":
        return True
    if _remainder_has_sep(text, label_end):
        return True
    # 独立成行且本行值较短：【发行片商】FOO；勿把换行后的【午夜寻花】长片名当新字段
    if _at_line_start(text, start):
        preview = _line_value_preview(text, label_end)
        if preview and len(preview) <= 64:
            return True
        if not preview:
            # 空值行：若下一非空行仍是【标签】，仍算字段栈
            tail = text[label_end:]
            nxt = re.match(r"\s*\n\s*[【［〖「『\[]", tail)
            if nxt:
                return True
    return False


def iter_structure_field_openers(
    text: str,
    *,
    min_start: int = 0,
    allow_start_zero: bool = True,
) -> list[tuple[int, int, str]]:
    """文档序字段开标签；(start, label_end, raw_label)。"""
    blob = text or ""
    hits: list[tuple[int, int, str]] = []
    for cre in _LABEL_FINDERS:
        for m in cre.finditer(blob):
            start, label_end = m.start(), m.end()
            if start < min_start:
                continue
            if start == 0 and not allow_start_zero:
                continue
            raw = (m.group(1) or "").strip()
            if not is_structure_field_opener(
                raw, blob, label_end, matched=m.group(0), start=start
            ):
                continue
            hits.append((start, label_end, normalize_structure_label_key(raw) or raw))
    hits.sort(key=lambda x: x[0])
    # 同起点只留最长匹配（极少见）
    out: list[tuple[int, int, str]] = []
    for h in hits:
        if out and h[0] == out[-1][0]:
            if h[1] > out[-1][1]:
                out[-1] = h
            continue
        # 嵌套在上一标签内部则跳过
        if out and h[0] < out[-1][1]:
            continue
        out.append(h)
    return out


def find_next_structure_field_start(
    text: str,
    *,
    min_start: int = 1,
) -> int | None:
    """片名/文件名截尾：下一字段开标签起点；默认跳过 start=0 装饰前缀。"""
    blob = collapse_structure_label_gaps(text or "")
    openers = iter_structure_field_openers(
        blob, min_start=max(0, min_start), allow_start_zero=min_start <= 0
    )
    return openers[0][0] if openers else None


# 短字段：一行有值即结束（类型/大小/有码/密码/预览…）
_ONE_LINE_ROLES = frozenset({"type", "coded", "size", "password", "preview", "torrent"})

# 下一行明显是新语义（硬换行），不是过长折行
_HARD_BREAK_LINE_RE = re.compile(
    r"(?:"
    r"[￥¥]"
    r"|某房|限时|特价|原价|促销|秒杀"
    r"|下载附件|下载次数|点击文件名"
    r"|回复\s*支持|使用道具|只看该作者|发表于|Powered by"
    r"|有人说|骗子别信"
    r"|\.png\s*\(|\.jpe?g\s*\(|\.gif\s*\(|\.webp\s*\("
    r"|aid=\d+"
    r")",
    re.I,
)

# 片名已带容量尾巴 → 本字段结束
_NAME_CAPACITY_TAIL_RE = re.compile(
    r"(?:"
    r"【\s*\d+\s*V\s*/"
    r"|\d+\s*[KMGT]B?\s*/\s*\d+\s*配额"
    r"|\[\s*(?:MP4|MKV|AVI)?\s*/\s*[\d.]+\s*[KMGT]?B?\s*\]"
    r")",
    re.I,
)


def _is_hard_break_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return True
    if _HARD_BREAK_LINE_RE.search(s):
        return True
    # 独立装饰【合集】等不当硬断；带冒号的新标签已在开卡时切开
    return False


def _line_value_complete(role: StructureRole, line: str) -> bool:
    """本行值是否已像「说完了」（再跟行优先当硬结束，除非判为软折行）。"""
    s = (line or "").strip()
    if not s:
        return False
    if role in _ONE_LINE_ROLES:
        return True
    # 未闭合括号 / 顿号逗号收尾 → 多半折行未完
    if s.count("【") > s.count("】") or s.count("[") > s.count("]"):
        return False
    if s.count("（") > s.count("）") or s.count("(") > s.count(")"):
        return False
    if s.endswith(("、", "，", ",", "/", "\\", "-", "–", "—", "（", "(")):
        return False
    if role == "name" and _NAME_CAPACITY_TAIL_RE.search(s):
        return True
    if role == "other" and len(s) <= 40:
        return True
    if role == "name" and len(s) <= 24:
        return True
    # 长片名/长说明：本行有内容仍可能软折到下一行
    return len(s) <= 48


def _is_soft_wrap_continuation(
    role: StructureRole, prev: str, nxt: str
) -> bool:
    """过长换行：下一行仍属本字段。"""
    if _is_hard_break_line(nxt):
        return False
    if role in _ONE_LINE_ROLES and (prev or "").strip():
        return False
    # 未写完 → 软折
    if not _line_value_complete(role, prev):
        return True
    # 长片名折行：上一行已较长且无容量尾，下一行像续写（非楼层/营销）
    if role == "name" and not _NAME_CAPACITY_TAIL_RE.search(prev):
        if len(prev.strip()) >= 28 and re.match(
            r"^[\u4e00-\u9fffA-Za-z0-9【\[（(☢⭐★☆]", nxt or ""
        ):
            return True
    if role == "other" and len(prev) > 40:
        if re.match(r"^[\u4e00-\u9fffA-Za-z0-9]", nxt or ""):
            return True
    return False


def clip_card_value_lines(role: StructureRole, value: str) -> str:
    """区分软折行（并入）与硬换行（截断）。"""
    lines = [
        ln.strip()
        for ln in (value or "").replace("\r", "\n").split("\n")
        if ln.strip()
    ]
    if not lines:
        return ""
    out = [lines[0]]
    for nxt in lines[1:]:
        if _is_hard_break_line(nxt):
            break
        if not _is_soft_wrap_continuation(role, out[-1], nxt):
            break
        out.append(nxt)
    return " ".join(out)


def parse_structure_cards(text: str) -> list[StructureCard]:
    """切结构卡片并归角色。匹配前折叠括号内标签字间空。"""
    blob = collapse_structure_label_gaps(text or "")
    if not blob.strip():
        return []
    openers = iter_structure_field_openers(blob, min_start=0, allow_start_zero=True)
    if not openers:
        return []
    cards: list[StructureCard] = []
    for i, (start, label_end, raw_label) in enumerate(openers):
        next_start = openers[i + 1][0] if i + 1 < len(openers) else len(blob)
        # 值区在 magnet/ed2k 前也可截（避免吞整页链）
        value_blob = blob[label_end:next_start]
        m_link = re.search(r"(?i)\s*(?:magnet:|ed2k:)", value_blob)
        if m_link:
            value_blob = value_blob[: m_link.start()]
            end = label_end + m_link.start()
        else:
            end = next_start
        val = value_blob.replace("\r", "\n")
        val = re.sub(r"^[\s]*" + _FIELD_SEP_CLASS + r"?\s*", "", val)
        val = val.strip()
        role = classify_structure_role(raw_label)
        val = clip_card_value_lines(role, val)
        cards.append(
            StructureCard(
                raw_label=raw_label,
                role=role,
                value=val,
                start=start,
                end=end,
                label_end=label_end,
            )
        )
    return cards


def cards_to_metadata_dict(cards: list[StructureCard]) -> dict[str, str]:
    """卡片 → 原始 metadata（键=归一标签）；调用方再 normalize/clip。

    hash 类标签仍进 raw meta（磁力旁证）；normalize_metadata_for_board 再滤掉展示。
    """
    meta: dict[str, str] = {}
    for c in cards:
        if c.role == "torrent":
            continue
        if c.role == "preview" and not (c.value or "").strip():
            continue
        key = c.raw_label
        val = (c.value or "").strip()
        if key and val and key not in meta:
            meta[key] = val
    return meta


def name_values_from_cards(cards: list[StructureCard]) -> list[str]:
    """仅名称角色的取值（文档序）。"""
    out: list[str] = []
    for c in cards:
        if c.role != "name":
            continue
        v = (c.value or "").strip()
        if v:
            out.append(v)
    return out
