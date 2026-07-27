"""资源形态填槽框架：先定型 → 按槽位填 → 结构/容量验收。

与 docs/资源入库模型.md 对齐。不合格仍可写入，但 outcome 不得以「成功」开头。

形态细类（看帖先判）：
  single_one_link   单资源单链接
  single_multi_link 单资源多链接（合集包）
  multi_one_link    多资源且每名一条链
  multi_multi_link  多资源且至少一名多链
  no_link           无可用下载链（F）

填不上时归因：
  cause:parse   识别错误（帖面有线索却没填对）
  cause:missing 真没有（模板允许空 / 帖面无对应数据）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from parsers.links import DualParseResult, ParsedAsset
from parsers.magnet import parse_capacity_bytes

VerdictStatus = Literal["ok", "structure_fail", "content_gap"]
FillCause = Literal["parse", "missing"]

# A/B/C/F 粗类（兼容旧筛选）
SHAPE_LABEL = {
    "A": "单资源",
    "B": "多资源",
    "C": "截断名已合并",
    "F": "无下载链",
}

# 细类：单/多资源 × 单/多链
KIND_LABEL = {
    "single_one_link": "单资源单链接",
    "single_multi_link": "单资源多链接",
    "multi_one_link": "多资源单链接",
    "multi_multi_link": "多资源多链接",
    "no_link": "无下载链",
}

CAUSE_LABEL = {
    "parse": "识别错误",
    "missing": "真没有",
}

# ×N / xN部；勿把「Sara x Rio x 3P」里的 x 3P（多人玩法）当成资源数
# 勿把「6部合集」当 ×N：那是包内片数/片名用语，常配 1配额单链
# 勿把分辨率「1024X576」「2048X1152」当 ×N（数字与 X 相连）
# 勿把「365天×10次 / 365日×10発」次数用法当 ×N
_X_COUNT_RE = re.compile(
    r"×\s*(\d+)(?!\s*[Pp]\b)(?![Pp])(?!\d)(?!\s*(?:次|发|發|発|回))"
    r"|(?<![0-9A-Za-z])[xX]\s*(\d+)(?!\s*[Pp]\b)(?![Pp])(?!\d)(?!\s*(?:次|发|發|発|回))"
    r"|(?:共|合计|總計|总计)\s*(\d+)\s*(?:部|个|個|題|题|片)"
    r"|（\s*(\d+)\s*部\s*）",
    re.I,
)
# DB/占位写入的 4KB 等极小 size，不当作真实入库容量
_PLACEHOLDER_SIZE_MAX = 8 * 1024
_V_COUNT_RE = re.compile(r"(?<![A-Za-z0-9.])(\d+)\s*V(?![A-Za-z])", re.I)
# ed2k 合集常见：70.6G/1169V//7配额 · 20.2g/17V/2配额
_QUOTA_COUNT_RE = re.compile(r"(\d+)\s*配额", re.I)
# 标题写「115eD2k/夸克/迅雷」时，N配额常含云盘份，不全等于入库 ed2k 链数
_CLOUD_SHARE_IN_TITLE_RE = re.compile(
    r"夸克|百度网盘|百度|迅雷|阿里云?盘?|UC云|蓝奏|网盘",
    re.I,
)
# 【影片大小】：MB / 【资源大小】：（空）——有标签无有效数字
_EMPTY_SIZE_LABEL_RE = re.compile(
    r"[【［〖「『\[]\s*[^】］〗」』\]]{0,12}(?:大小|容量|尺寸)\s*[】］〗」』\]]"
    r"\s*[:：︰｜|/／·・•‧＝=\-_;；,，]?\s*"
    r"(?:MB|GB|TB|M|G|T)?\s*(?=\n|$|[【［])",
    re.I,
)


@dataclass(slots=True)
class FrameSpec:
    shape: str  # A|B|C|F
    kind: str  # single_one_link | … | no_link
    capacity: str  # D1|D2|D3|ok
    source: str  # body|attach
    layout: str = ""
    truncated_merged: bool = False


@dataclass(slots=True)
class SlotFill:
    """单个槽位的填充结果。"""

    slot: str  # filename|links|previews|size
    ok: bool
    value_summary: str = ""
    cause: FillCause | None = None
    message: str = ""


@dataclass(slots=True)
class FrameRow:
    """按资源名填好的一行槽位。"""

    filename: str
    size: int
    previews: list[str]
    links: list[str]
    hashes: list[str]
    head: ParsedAsset
    members: list[ParsedAsset]
    slot_errors: list[str] = field(default_factory=list)
    slots: list[SlotFill] = field(default_factory=list)


@dataclass(slots=True)
class FrameVerdict:
    status: VerdictStatus
    hard_errors: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"


@dataclass(slots=True)
class ResourceFrame:
    spec: FrameSpec
    rows: list[FrameRow]
    verdict: FrameVerdict

    @property
    def shape(self) -> str:
        return self.spec.shape

    @property
    def kind(self) -> str:
        return self.spec.kind


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def _pack_capacity_bytes(title: str, desc: str = "", meta_size: str = "") -> int:
    """帖级总容量：标题有明确容量时以标题为准。

    描述【资源大小】常写脏值（tid=2829365：标题 31G，描述却 11G），
    parse_capacity_bytes 会优先吃【资源大小】字段导致误判。
    """
    t = parse_capacity_bytes(title or "")
    if t > 0:
        return t
    return parse_capacity_bytes(_blob(title, desc, meta_size))


def _uniq(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0"
    gb = n / (1024**3)
    if gb >= 1:
        return f"{gb:.2f}GB"
    mb = n / (1024**2)
    return f"{mb:.1f}MB"


def _note(
    tags: list[str],
    bucket: list[str],
    code: str,
    zh: str,
    *,
    cause: FillCause,
) -> None:
    """筛选用码 + 中文（带【识别错误】/【真没有】前缀）。"""
    tags.append(code)
    tags.append(f"cause:{cause}")
    prefix = CAUSE_LABEL[cause]
    if not zh.startswith("【"):
        zh = f"【{prefix}】{zh}"
    bucket.append(zh)


def _title_expect_count(*texts: str) -> int | None:
    """从标题/描述取 ×N、共N部等数量口径（大合集可上千）。"""
    best: int | None = None
    for text in texts:
        for m in _X_COUNT_RE.finditer(text or ""):
            for g in m.groups():
                if g and str(g).isdigit():
                    n = int(g)
                    if 2 <= n <= 20000:
                        best = n if best is None else max(best, n)
                    break
    return best


def _has_empty_size_label(text: str | None) -> bool:
    """【影片大小】：MB / 空值 —— 有标签但无有效容量数字。"""
    raw = (text or "").strip()
    if not raw:
        return False
    if parse_capacity_bytes(raw) > 0:
        return False
    return bool(_EMPTY_SIZE_LABEL_RE.search(raw))


def _effective_size(n: int | None) -> int:
    """真实容量；占位/空记 0。"""
    v = int(n or 0)
    if v <= 0 or v <= _PLACEHOLDER_SIZE_MAX:
        return 0
    return v


def _member_size_sum(members: Sequence[ParsedAsset]) -> int:
    """多链时合计各链 size（ed2k xl）；单链取该值。忽略占位 size。"""
    pos = [
        _effective_size(getattr(a, "size", 0))
        for a in members
        if _effective_size(getattr(a, "size", 0)) > 0
    ]
    if not pos:
        return 0
    return int(sum(pos)) if len(pos) > 1 else int(pos[0])


def _all_magnet_no_xl(rows: Sequence[FrameRow]) -> bool:
    """全部为磁力且链上无有效 size（无 xl）——容量无法从 URI 核验。"""
    any_link = False
    for r in rows:
        for a in r.members:
            any_link = True
            kind = str(getattr(a, "link_kind", "") or "").strip().lower()
            if kind and kind not in {"magnet"}:
                return False
            if int(getattr(a, "size", 0) or 0) > 0:
                return False
            uri = (getattr(a, "uri", None) or "").lower()
            if uri.startswith("ed2k:"):
                return False
    return any_link


def _count_matches(actual: int, expect: int) -> bool:
    """标题/描述数量与链数是否可接受。

    - 链数 ≥ 描述数量 → 合格（多链合集常见：标题写共 N 部，附件多几条）
    - 大合集（≥20）链数略少仍允许约 5% 偏差
    """
    a, e = int(actual or 0), int(expect or 0)
    if a <= 0 or e <= 0:
        return False
    if a >= e:
        return True
    if e >= 20 and (e - a) <= max(2, e // 20):
        return True
    return False


def _title_v_count(blob: str) -> int | None:
    best = None
    for m in _V_COUNT_RE.finditer(blob or ""):
        n = int(m.group(1))
        if 2 <= n <= 20000:
            best = n if best is None else max(best, n)
    return best


def _title_quota_count(blob: str) -> int | None:
    """标题/描述里的 N配额（ed2k 下载份数口径）。"""
    best = None
    for m in _QUOTA_COUNT_RE.finditer(blob or ""):
        n = int(m.group(1))
        if 1 <= n <= 20000:
            best = n if best is None else max(best, n)
    return best


def _primary_link_kind(parsed: DualParseResult, rows: list[FrameRow]) -> str:
    kind = str(getattr(parsed, "primary_link_kind", "") or "").strip().lower()
    if kind in {"magnet", "ed2k", "115share", "both"}:
        return kind
    for r in rows:
        for a in r.members:
            k = str(getattr(a, "link_kind", "") or "").strip().lower()
            if k in {"magnet", "ed2k", "115share"}:
                return k
    return ""


def _piece_count_expect(
    blob: str, *, link_kind: str, title: str = ""
) -> tuple[int | None, str]:
    """按主链类型取「应有链数」口径。

    - ed2k：优先 N配额（片数 V 不当链数）；标题有配额时以标题为准
      （描述【资源大小】常写脏 N配额，勿 max 抬高）
    - magnet：N V
    """
    kind = (link_kind or "").lower()
    if kind in {"ed2k", "115share"}:
        if title:
            q_title = _title_quota_count(title)
            if q_title is not None:
                return q_title, "配额"
        q = _title_quota_count(blob)
        if q is not None:
            return q, "配额"
        return None, ""
    v = _title_v_count(blob)
    if v is not None:
        return v, "V"
    return None, ""


def _preview_tuple(imgs: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(x for x in (imgs or []) if x)


def _meta_size_text(parsed: DualParseResult) -> str:
    meta = getattr(parsed, "metadata", None) or {}
    if not isinstance(meta, dict):
        return ""
    for k in ("资源大小", "影片大小", "文件大小", "影片容量"):
        v = str(meta.get(k) or "")
        if v:
            return v
    return ""


def _pack_size_looks_like_row_echo(pack_size: int, row_sizes: Sequence[int]) -> bool:
    """多资源帖：帖级 metadata 常是末块【影片大小】，不能当总容量。

    判定：帖级字节≈某个子资源，且子资源合计明显更大。
    """
    if pack_size <= 0:
        return False
    known = [int(s) for s in row_sizes if int(s or 0) > 0]
    if len(known) < 2:
        return False
    slack = max(int(pack_size * 0.05), 32 * 1024 * 1024)
    if not any(abs(s - pack_size) <= slack for s in known):
        return False
    total = sum(known)
    return total > pack_size + max(int(pack_size * 0.2), 500 * 1024 * 1024)


def _capacity_class(blob: str) -> str:
    if "容量不详" in blob or "容量不明" in blob:
        return "D2"
    if parse_capacity_bytes(blob) > 0:
        return "D1"
    return "D3"


def _unique_link_hashes(
    assets: Sequence[ParsedAsset], *, kinds: set[str] | None = None
) -> set[str]:
    out: set[str] = set()
    for a in assets:
        if kinds and (a.link_kind or "") not in kinds:
            continue
        h = (a.hash or "").strip().upper()
        if h:
            out.add(h)
    return out


def _recog_hashes(
    parsed: DualParseResult, kinds_in_groups: set[str]
) -> set[str]:
    kinds = kinds_in_groups or {"magnet", "ed2k"}
    recog = _unique_link_hashes(list(parsed.assets or []), kinds=kinds)
    if "magnet" in kinds:
        for m in getattr(parsed, "magnets", None) or []:
            h = (
                getattr(m, "infohash", None) or getattr(m, "hash", None) or ""
            ).strip().upper()
            if h:
                recog.add(h)
    if "ed2k" in kinds:
        for e in getattr(parsed, "ed2k_links", None) or []:
            h = (getattr(e, "hash", None) or "").strip().upper()
            if h:
                recog.add(h)
    return recog


def classify_kind(*, n_groups: int, per_group_links: Sequence[int]) -> str:
    """看分组结果判定细类。"""
    if n_groups <= 0:
        return "no_link"
    total = sum(int(x) for x in per_group_links)
    max_per = max((int(x) for x in per_group_links), default=0)
    if n_groups == 1:
        return "single_multi_link" if total > 1 else "single_one_link"
    return "multi_multi_link" if max_per > 1 else "multi_one_link"


def classify_frame(
    *,
    n_groups: int,
    per_group_links: Sequence[int],
    truncated_merged: bool,
    had_attachments: bool,
    layout: str,
    pack_blob: str,
    any_row_size: bool,
    pack_size: int,
) -> FrameSpec:
    if n_groups == 0:
        shape = "F"
    elif truncated_merged and n_groups == 1:
        shape = "C"
    elif n_groups == 1:
        shape = "A"
    else:
        shape = "B"

    kind = classify_kind(n_groups=n_groups, per_group_links=per_group_links)

    cap_raw = _capacity_class(pack_blob)
    if cap_raw == "D2":
        capacity = "D2"
    elif pack_size > 0 or any_row_size:
        if pack_size > 0 and not any_row_size:
            capacity = "D1"
        else:
            capacity = "ok" if any_row_size else "D3"
    else:
        capacity = "D3"

    return FrameSpec(
        shape=shape,
        kind=kind,
        capacity=capacity,
        source="attach" if had_attachments else "body",
        layout=(layout or "").strip(),
        truncated_merged=bool(truncated_merged),
    )


def fill_rows(
    named_groups: Sequence[tuple[str, ParsedAsset, list[ParsedAsset]]],
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> list[FrameRow]:
    """按资源名逐行填槽：名 / 链 / 图≤5 / 大小；记录槽位与归因。"""
    title = (post_title or parsed.title or "").strip()
    desc = (parsed.description or "").strip()
    meta_size = _meta_size_text(parsed)
    n_groups = len(named_groups)
    thread_previews = [x for x in (parsed.preview_images or []) if x]
    pack_blob = _blob(title, desc, meta_size)
    pack_has_size_text = parse_capacity_bytes(pack_blob) > 0
    cap_class = _capacity_class(pack_blob)
    rows: list[FrameRow] = []

    for name, head0, members in named_groups:
        uris: list[str] = []
        hashes: list[str] = []
        for a in members:
            u = (a.uri or "").strip()
            if u and u not in uris:
                uris.append(u)
            h = (a.hash or "").strip().upper()
            if h and h not in hashes:
                hashes.append(h)
        if not uris and head0.uri:
            uris = [(head0.uri or "").strip()]

        previews: list[str] = []
        for a in members:
            for img in a.preview_images or []:
                if img and img not in previews:
                    previews.append(img)
        if not previews and n_groups <= 1:
            for img in thread_previews:
                if img and img not in previews:
                    previews.append(img)
        raw_preview_n = len(previews)
        previews = previews[:5]

        # 容量：有【影片/资源大小】等文案时以文案为准（合集标签 55GB 勿被残缺 magnet xl 盖掉）
        row_desc = ""
        for a in members:
            if a.description:
                row_desc = a.description
                break
        label_size = 0
        for text in (row_desc, name):
            got = parse_capacity_bytes(text or "")
            # 忽略「4K→4KB」类噪声 / 占位级「容量」
            if got > _PLACEHOLDER_SIZE_MAX:
                label_size = got
                break
        if not label_size and n_groups <= 1:
            for text in (desc, title, meta_size, parsed.description or ""):
                got = parse_capacity_bytes(text or "")
                if got > _PLACEHOLDER_SIZE_MAX:
                    label_size = got
                    break
        asset_size = _member_size_sum(members)
        if not asset_size:
            asset_size = _effective_size(head0.size)
        size = label_size or asset_size
        # 无文案时丢掉占位 size，避免 4KB 写成 0.0MB 过槽
        if not label_size:
            size = _effective_size(size)

        slots: list[SlotFill] = []
        slot_errors: list[str] = []

        fname = (name or "").strip()
        if fname:
            slots.append(SlotFill("filename", True, fname[:80]))
        else:
            msg = "资源名为空"
            slots.append(SlotFill("filename", False, "", "parse", msg))
            slot_errors.append(f"【识别错误】{msg}")

        if uris:
            slots.append(SlotFill("links", True, f"{len(uris)}条"))
        else:
            msg = "无下载链"
            cause: FillCause = "parse" if members else "missing"
            slots.append(SlotFill("links", False, "", cause, msg))
            slot_errors.append(f"【{CAUSE_LABEL[cause]}】{msg}")

        # 图片槽：≤5；多资源且帖有图却本名为空 → 识别错误（硬）；单资源无图且帖无图 → 真没有（允许）
        if previews:
            summary = f"{len(previews)}张"
            if raw_preview_n > 5:
                slots.append(
                    SlotFill(
                        "previews",
                        True,
                        summary,
                        "parse",
                        f"预览超过5张已截断（原{raw_preview_n}张）",
                    )
                )
            else:
                slots.append(SlotFill("previews", True, summary))
        elif thread_previews and n_groups > 1:
            msg = "帖有预览却未分到该资源名下"
            slots.append(SlotFill("previews", False, "", "parse", msg))
            slot_errors.append(f"【识别错误】{msg}")
        elif thread_previews and n_groups <= 1:
            # 单资源本应回落帖级预览；仍空则识别错误
            msg = "帖有预览却未填到资源上"
            slots.append(SlotFill("previews", False, "", "parse", msg))
            slot_errors.append(f"【识别错误】{msg}")
        else:
            slots.append(
                SlotFill("previews", True, "0", "missing", "帖面无预览图")
            )

        # 容量槽：本行有可解析容量却仍为 0 → 识别错误；空标签/多资源无本行口径 → 允许 0
        row_has_claim = label_size > 0
        row_empty_label = (not row_has_claim) and _has_empty_size_label(row_desc)
        if size > 0:
            slots.append(SlotFill("size", True, _fmt_bytes(size)))
        elif cap_class == "D2":
            slots.append(
                SlotFill("size", True, "0", "missing", "写明容量不详，允许0")
            )
        elif row_empty_label:
            slots.append(
                SlotFill("size", True, "0", "missing", "大小标签无有效数值，允许0")
            )
        elif row_has_claim:
            msg = "有容量文案但大小为0"
            slots.append(SlotFill("size", False, "0", "parse", msg))
        elif n_groups <= 1 and (pack_has_size_text or cap_class == "D1"):
            # 单资源：帖面总容量有数却未落到本行
            msg = "有容量文案但大小为0"
            slots.append(SlotFill("size", False, "0", "parse", msg))
        else:
            slots.append(
                SlotFill("size", True, "0", "missing", "全文无容量信息，允许0")
            )

        rows.append(
            FrameRow(
                filename=fname or (head0.hash or ""),
                size=int(size or 0),
                previews=previews,
                links=uris,
                hashes=hashes,
                head=head0,
                members=list(members),
                slot_errors=slot_errors,
                slots=slots,
            )
        )
    return rows


def validate_frame(
    spec: FrameSpec,
    rows: list[FrameRow],
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> FrameVerdict:
    """结构硬门 + 容量缺口；失败区分识别错误 / 真没有。"""
    title = (post_title or parsed.title or "").strip()
    desc = (parsed.description or "").strip()
    meta_size = _meta_size_text(parsed)
    pack_blob = _blob(title, desc, meta_size)
    pack_size = _pack_capacity_bytes(title, desc, meta_size)
    if _pack_size_looks_like_row_echo(pack_size, [_effective_size(r.size) for r in rows]):
        pack_size = 0
    thread_previews = [x for x in (parsed.preview_images or []) if x]

    n_groups = len(rows)
    hard: list[str] = []
    soft: list[str] = []
    tags: list[str] = []

    if spec.shape == "F":
        tags.append("shape:F")
    elif spec.shape == "C":
        tags.extend(["shape:C", "shape:A"])
    elif spec.shape == "A":
        tags.append("shape:A")
    else:
        tags.append("shape:B")
    tags.append(f"kind:{spec.kind}")

    tags.append(f"src:{spec.source}")
    if spec.layout:
        tags.append(f"layout:{spec.layout}")
    elif n_groups <= 1 and sum(len(r.links) for r in rows) > 1:
        tags.append("layout:inferred_pack")
    elif n_groups > 1:
        tags.append("layout:inferred_multi")

    n_links = sum(len(r.links) for r in rows)
    tags.append("links:single" if n_links <= 1 else "links:multi")
    tags.append("res:single" if n_groups <= 1 else "res:multi")

    if spec.capacity == "D2":
        tags.append("cap:D2")
    elif spec.capacity == "D1":
        tags.extend(["cap:D1", "cap:text_present"])
    elif spec.capacity == "ok":
        tags.append("cap:ok")
    else:
        tags.append("cap:D3")

    for r in rows:
        for e in r.slot_errors:
            # 预览未分配：多数已分仅少数缺 → 下面按比例降级，先不进 hard
            if "未分到该资源名下" in e or "帖有预览却未填到资源上" in e:
                continue
            hard.append(e)
            if "识别错误" in e:
                tags.append("cause:parse")
            elif "真没有" in e:
                tags.append("cause:missing")

    preview_slot_miss = [
        e
        for r in rows
        for e in r.slot_errors
        if ("未分到该资源名下" in e or "帖有预览却未填到资源上" in e)
    ]
    if preview_slot_miss:
        if len(preview_slot_miss) <= 1 and n_groups >= 8:
            for e in preview_slot_miss:
                soft.append(e)
            tags.append("cause:parse")
            tags.append("warn:preview_unassigned_minor")
        else:
            for e in preview_slot_miss:
                hard.append(e)
            tags.append("cause:parse")
            tags.append("flag:preview_fail")

    kinds: set[str] = set()
    for r in rows:
        for a in r.members:
            if a.link_kind:
                kinds.add(a.link_kind)
    if not kinds:
        kinds = {"magnet", "ed2k"}

    group_hashes: set[str] = set()
    for r in rows:
        group_hashes.update(r.hashes)
    recog = _recog_hashes(parsed, kinds)
    recog_n = len(recog)
    member_sum = sum(len(r.members) for r in rows)
    uri_sum = n_links

    metrics: dict[str, Any] = {
        "n_groups": n_groups,
        "n_assets": member_sum,
        "recog_links": recog_n,
        "persist_link_members": member_sum,
        "persist_link_uris": uri_sum,
        "per_group_links": [len(r.links) for r in rows],
        "pack_size": pack_size,
        "cap_text": spec.capacity,
        "group_sizes": [r.size for r in rows],
        "group_names": [r.filename for r in rows],
        "kind": spec.kind,
        "kind_label": KIND_LABEL.get(spec.kind, spec.kind),
    }

    if recog_n > 0 or member_sum > 0:
        dropped = sorted(recog - group_hashes)
        metrics["dropped_hashes"] = dropped[:20]
        metrics["extra_hashes"] = sorted(group_hashes - recog)[:20]
        if recog_n != member_sum or recog_n != uri_sum or bool(dropped):
            _note(
                tags,
                hard,
                "warn:link_sum_mismatch",
                f"链数不合规：识别到{recog_n}条下载链，"
                f"入库各子资源合计{uri_sum}条"
                + (f"（有{len(dropped)}条未进组）" if dropped else ""),
                cause="parse",
            )
            tags.append("flag:link_inconsistent")

    expect_n = _title_expect_count(title, desc)
    metrics["title_expect_n"] = expect_n
    shape_ab = "A" if spec.shape in ("A", "C") else spec.shape

    if shape_ab == "B" and n_groups >= 2:
        names = [r.filename for r in rows]
        if len(set(names)) < len(names):
            _note(
                tags,
                hard,
                "warn:dup_resource_name",
                "多资源存在重复资源名（一名一行违规）",
                cause="parse",
            )
        if title:
            # 多资源：标题与资源名理论应区分；任一名=帖标题 → 结构不合格
            same_title = sum(1 for r in rows if (r.filename or "").strip() == title)
            if same_title > 0:
                _note(
                    tags,
                    hard,
                    "warn:filename_fallback_title",
                    f"多资源有{same_title}/{n_groups}个资源名等于帖标题，"
                    "标题与子名应区分（可能没识别出真正片名）",
                    cause="parse",
                )

        nonempty = [
            _preview_tuple(r.previews) for r in rows if _preview_tuple(r.previews)
        ]
        if nonempty and len({p for p in nonempty}) <= 1:
            _note(
                tags,
                hard,
                "warn:shared_preview",
                "多资源预览图完全相同，可能没按片名分开配图",
                cause="parse",
            )
            tags.append("flag:preview_fail")

        empty_n = sum(1 for r in rows if not r.previews)
        if empty_n > 0:
            if thread_previews:
                # 绝大多数已分到图、仅少数缺 → 软提醒，避免整帖误杀
                if empty_n <= 1 and n_groups >= 8:
                    _note(
                        tags,
                        soft,
                        "warn:preview_unassigned_minor",
                        f"多资源里有{empty_n}/{n_groups}个没有预览图（少数缺图，待核）",
                        cause="parse",
                    )
                else:
                    _note(
                        tags,
                        hard,
                        "warn:preview_unassigned",
                        f"多资源里有{empty_n}/{n_groups}个没有预览图（帖面有图未按名分配）",
                        cause="parse",
                    )
                    tags.append("flag:preview_fail")
            elif empty_n > n_groups // 2:
                _note(
                    tags,
                    soft,
                    "warn:many_empty_preview",
                    f"多资源里有{empty_n}/{n_groups}个没有预览图（帖面也无图，属真没有）",
                    cause="missing",
                )

        if expect_n is not None and n_groups != expect_n:
            _note(
                tags,
                hard,
                "warn:title_count_mismatch",
                f"标题写×{expect_n}个资源，实际入库{n_groups}个资源名",
                cause="parse",
            )

    elif shape_ab == "A" and n_groups == 1:
        r0 = rows[0]
        member_n = len(r0.members)
        if len(r0.previews) > 5:
            _note(
                tags,
                hard,
                "warn:preview_gt5",
                f"单资源预览超过5张（{len(r0.previews)}），模板上限5",
                cause="parse",
            )
            tags.append("flag:preview_fail")
        elif not r0.previews and not thread_previews:
            _note(
                tags,
                soft,
                "warn:preview_missing_ok",
                "单资源无预览图（帖面也无图，属真没有）",
                cause="missing",
            )

        # 单资源：资源名可以等于帖标题
        name_eq_title = bool(title) and (r0.filename or "").strip() == title
        if name_eq_title:
            tags.append("info:pack_name_is_title")

        # 标题×N 却只填出 1 名单链 → 仍结构不合格（子名未切开）
        if expect_n is not None and expect_n >= 2 and spec.kind == "single_one_link":
            _note(
                tags,
                hard,
                "warn:title_xn_but_shape_A",
                f"标题写×{expect_n}个资源，却只填出1名单链（子名未切开）",
                cause="parse",
            )

        # 单资源多链接数量：ed2k→配额硬校验；磁力→V 仅软提醒（一条磁力常含多 V）
        if spec.kind == "single_multi_link" and member_n >= 1:
            link_kind_a = _primary_link_kind(parsed, rows)
            expect_pieces_a, piece_unit_a = _piece_count_expect(
                pack_blob, link_kind=link_kind_a, title=title
            )
            metrics["piece_link_kind"] = link_kind_a
            metrics["title_piece_expect"] = expect_pieces_a
            if expect_pieces_a is None:
                if link_kind_a in {"ed2k", "115share"}:
                    tags.append("info:no_quota_skip_count")
                else:
                    tags.append("info:no_v_skip_count")
            elif _count_matches(member_n, expect_pieces_a):
                tags.append("info:piece_count_match")
                metrics["piece_count_match"] = True
            else:
                unit = piece_unit_a or "份"
                msg = (
                    f"标题写{expect_pieces_a}{unit}，单资源多链接链数仅{member_n}"
                    f"（少于口径，疑似漏链）"
                )
                if link_kind_a == "magnet":
                    # 磁力 V≠链数常见（一磁多文件），不升结构不合格
                    _note(
                        tags,
                        soft,
                        "warn:piece_count_mismatch_magnet",
                        msg,
                        cause="parse",
                    )
                    tags.append("info:magnet_v_soft")
                elif _CLOUD_SHARE_IN_TITLE_RE.search(pack_blob or ""):
                    # 115eD2k/夸克/迅雷 混合：配额常含云盘份，勿硬判漏链
                    _note(
                        tags,
                        soft,
                        "warn:piece_count_mismatch_cloud",
                        msg,
                        cause="parse",
                    )
                    tags.append("info:cloud_quota_soft")
                elif member_n < int(expect_pieces_a):
                    # 标题配额偏高：无附件可补，或附件已下全仍短（以实链为准）
                    src_zh = "附件" if spec.source == "attach" else "正文"
                    why = (
                        "附件已下，以实链为准"
                        if spec.source == "attach"
                        else "无附件可补，以实链为准"
                    )
                    soft_msg = (
                        f"标题写{expect_pieces_a}{unit}，{src_zh}链数仅{member_n}"
                        f"（标题偏高，{why}）"
                    )
                    _note(
                        tags,
                        soft,
                        "warn:piece_count_mismatch_title_over",
                        soft_msg,
                        cause="missing",
                    )
                    tags.append("info:title_quota_overclaim_soft")
                else:
                    _note(
                        tags,
                        hard,
                        "warn:piece_count_mismatch",
                        msg,
                        cause="parse",
                    )

    for r in rows:
        for s in r.slots:
            if s.slot != "previews":
                continue
            if s.ok and s.cause == "parse" and s.message and "截断" in s.message:
                _note(
                    tags,
                    soft,
                    "warn:preview_truncated",
                    f"「{r.filename[:40]}」{s.message}",
                    cause="parse",
                )
            elif (
                not s.ok
                and s.cause == "parse"
                and "warn:preview_unassigned_minor" not in tags
            ):
                tags.append("flag:preview_fail")
                tags.append("cause:parse")

    from collections import Counter

    from parsers.resource_names import (
        SUBRESOURCE_TITLE_MATCH_FORMS,
        normalize_structure_label_key,
    )

    wanted = {normalize_structure_label_key(x) for x in SUBRESOURCE_TITLE_MATCH_FORMS}
    # 同模板常并列【影片名称】+【资源名称】指同一部；仅当同一标签重复出现才像多资源
    label_hits: Counter[str] = Counter()
    for m in re.finditer(
        r"[【［〖「『\[]\s*([^】］〗」』\]]{1,40})\s*[】］〗」』\]]", desc or ""
    ):
        key = normalize_structure_label_key(m.group(1))
        if key in wanted:
            label_hits[key] += 1
    repeated = max(label_hits.values(), default=0)
    if repeated >= 2 and n_groups == 1:
        _note(
            tags,
            hard,
            "warn:multi_label_but_one_group",
            f"正文里有{repeated}个重复的资源名称标签，却只入库成1个资源",
            cause="parse",
        )
        metrics["desc_name_labels"] = int(sum(label_hits.values()))
        metrics["desc_name_label_max_repeat"] = int(repeated)

    v_count = _title_v_count(pack_blob)
    # 配额展示口径与 piece expect 一致：标题有则用标题
    quota_count = _title_quota_count(title) if title else None
    if quota_count is None:
        quota_count = _title_quota_count(pack_blob)
    metrics["title_v_count"] = v_count
    metrics["title_quota_count"] = quota_count
    if "piece_link_kind" not in metrics:
        metrics["piece_link_kind"] = _primary_link_kind(parsed, rows)
    if "title_piece_expect" not in metrics:
        metrics["title_piece_expect"] = _piece_count_expect(
            pack_blob,
            link_kind=str(metrics.get("piece_link_kind") or ""),
            title=title,
        )[0]

    # ---- 容量验收（D1 必填；D2/D3 允许 0；与帖面总量对照）----
    group_sizes = [_effective_size(r.size) for r in rows]
    any_size = any(s > 0 for s in group_sizes)
    content_gap = False
    cap_notes: list[str] = []
    magnet_no_xl = _all_magnet_no_xl(rows)

    def _cap_fail(code: str, zh: str) -> None:
        nonlocal content_gap
        content_gap = True
        _note(tags, cap_notes, code, zh, cause="parse")
        tags.append("flag:capacity_fail")

    def _cap_soft(code: str, zh: str) -> None:
        _note(tags, soft, code, zh, cause="missing")
        tags.append("info:capacity_unverified")

    for r in rows:
        for s in r.slots:
            if s.slot == "size" and not s.ok and s.cause == "parse":
                if magnet_no_xl and int(r.size or 0) <= 0:
                    _cap_soft(
                        "warn:d1_size_missing_magnet",
                        f"「{r.filename[:40]}」磁力无尺寸来源，未核容量",
                    )
                else:
                    _cap_fail(
                        "warn:d1_size_missing",
                        f"「{r.filename[:40]}」{s.message or '有容量文案但大小为0'}",
                    )

    if spec.capacity == "D2":
        pass
    elif pack_size > 0 or spec.capacity == "D1":
        if shape_ab == "A" and group_sizes:
            g0 = _effective_size(group_sizes[0])
            xl_sum = _member_size_sum(rows[0].members) if rows else 0
            # 行 size（常为帖面总容量）优先；占位/空时用各链 xl 合计对照
            cmp = int(g0 or 0) or int(xl_sum or 0)
            if xl_sum > 0:
                metrics["row_xl_sum"] = xl_sum
            if cmp <= 0:
                if magnet_no_xl:
                    _cap_soft(
                        "warn:d1_size_missing_magnet",
                        f"有容量文案{_fmt_bytes(pack_size) if pack_size else ''}但磁力无尺寸来源，未核容量",
                    )
                else:
                    _cap_fail(
                        "warn:d1_size_missing",
                        f"有容量文案{_fmt_bytes(pack_size) if pack_size else ''}但入库大小为0（D1）",
                    )
            elif pack_size > 0:
                slack = max(int(pack_size * 0.15), 200 * 1024 * 1024)
                if abs(cmp - pack_size) > slack:
                    _cap_fail(
                        "warn:size_pack_vs_row_mismatch",
                        f"容量不合规：帖子写{_fmt_bytes(pack_size)}，"
                        f"入库资源写{_fmt_bytes(cmp)}",
                    )
        if shape_ab == "B" and group_sizes:
            known = [s for s in group_sizes if s > 0]
            zero_n = sum(1 for s in group_sizes if s <= 0)
            if zero_n == n_groups and pack_size > 0:
                if magnet_no_xl:
                    _cap_soft(
                        "warn:size_sub_missing_magnet",
                        f"帖子写了总容量{_fmt_bytes(pack_size)}，磁力无尺寸来源，未核容量",
                    )
                else:
                    _cap_fail(
                        "warn:size_sub_missing_pack_has",
                        f"帖子写了总容量{_fmt_bytes(pack_size)}，各子资源大小却都是空的",
                    )
            elif zero_n > 0 and pack_size > 0 and not magnet_no_xl:
                empty_ok = 0
                for r in rows:
                    if int(r.size or 0) > 0:
                        continue
                    row_desc = next(
                        (a.description for a in r.members if getattr(a, "description", None)),
                        "",
                    )
                    if _has_empty_size_label(row_desc):
                        empty_ok += 1
                if empty_ok >= zero_n:
                    tags.append("info:empty_size_label_ok")
                else:
                    _cap_fail(
                        "warn:size_sub_incomplete",
                        f"帖子有总容量{_fmt_bytes(pack_size)}，"
                        f"但{n_groups}个子资源里只有{len(known)}个写出了大小",
                    )
            elif known and len(known) == len(group_sizes) and pack_size > 0:
                total = sum(known)
                metrics["sub_size_sum"] = total
                slack = max(int(pack_size * 0.2), 500 * 1024 * 1024)
                if abs(total - pack_size) > slack:
                    _cap_fail(
                        "warn:size_sum_mismatch",
                        f"容量不合规：帖子总容量{_fmt_bytes(pack_size)}，"
                        f"各子资源合计{_fmt_bytes(total)}",
                    )
    elif not any_size:
        _note(
            tags,
            soft,
            "warn:size_missing_ok",
            "全文无容量信息，大小为0（属真没有，允许）",
            cause="missing",
        )

    for msg in cap_notes:
        soft.append(msg)
    if content_gap and "cap:D1" not in tags and (pack_size > 0 or spec.capacity == "D1"):
        tags.extend(["cap:D1", "cap:text_present"])

    if spec.kind == "single_one_link" and uri_sum > 1:
        _note(
            tags,
            hard,
            "warn:kind_template_mismatch",
            "定型为单资源单链接，但填出多条链",
            cause="parse",
        )
    if spec.kind == "multi_one_link" and any(len(r.links) > 1 for r in rows):
        _note(
            tags,
            hard,
            "warn:kind_template_mismatch",
            "定型为多资源单链接，但有资源名下出现多链",
            cause="parse",
        )

    hard = _uniq(hard)
    soft = _uniq(soft)
    tags = _uniq(tags)

    if hard:
        status: VerdictStatus = "structure_fail"
        tags.append("flag:structure_fail")
        tags.append("flag:needs_rule")
        tags.append("verdict:structure_fail")
    elif content_gap:
        status = "content_gap"
        tags.append("flag:needs_rule")
        tags.append("verdict:content_gap")
    else:
        status = "ok"
        tags.append("verdict:ok")
        if soft:
            tags.append("flag:needs_rule")
            # 软提醒里的识别错误：outcome 用「待核」，tags 标 review，便于与干净成功分开筛
            if any(str(w).startswith("【识别错误】") for w in soft):
                tags.append("verdict:review")

    tags = _uniq(tags)
    return FrameVerdict(
        status=status,
        hard_errors=hard,
        soft_warnings=soft,
        tags=tags,
        metrics=metrics,
    )


def build_resource_frame(
    parsed: DualParseResult,
    *,
    named_groups: Sequence[tuple[str, ParsedAsset, list[ParsedAsset]]],
    had_attachments: bool = False,
    truncated_merged: bool = False,
    layout: str = "",
    post_title: str = "",
) -> ResourceFrame:
    """定型 → 填槽 → 验收，一帖一份框架结果。"""
    title = (post_title or parsed.title or "").strip()
    rows = fill_rows(named_groups, parsed, post_title=title)
    desc = parsed.description or ""
    meta_size = _meta_size_text(parsed)
    pack_blob = _blob(title, desc, meta_size)
    pack_size = _pack_capacity_bytes(title, desc, meta_size)
    # 多资源：忽略「末块大小误进帖级 metadata」造成的假总容量
    if _pack_size_looks_like_row_echo(pack_size, [_effective_size(r.size) for r in rows]):
        pack_size = 0
    any_row_size = any(_effective_size(r.size) > 0 for r in rows)
    per_links = [len(r.links) for r in rows]
    spec = classify_frame(
        n_groups=len(rows),
        per_group_links=per_links,
        truncated_merged=truncated_merged,
        had_attachments=had_attachments,
        layout=layout or str(getattr(parsed, "layout", "") or ""),
        pack_blob=pack_blob,
        any_row_size=any_row_size,
        pack_size=pack_size,
    )
    if pack_size > 0 and not any_row_size and spec.capacity != "D2":
        spec = FrameSpec(
            shape=spec.shape,
            kind=spec.kind,
            capacity="D1",
            source=spec.source,
            layout=spec.layout,
            truncated_merged=spec.truncated_merged,
        )
    verdict = validate_frame(spec, rows, parsed, post_title=title)
    return ResourceFrame(spec=spec, rows=rows, verdict=verdict)


def format_frame_outcome(base_tip: str, frame: ResourceFrame) -> str:
    """拼 import_outcome：不合格不得以「成功」开头；展示细类形态。"""
    v = frame.verdict
    label = KIND_LABEL.get(frame.spec.kind) or SHAPE_LABEL.get(
        frame.spec.shape, frame.spec.shape
    )
    recog = v.metrics.get("recog_links")
    persist = v.metrics.get("persist_link_uris")
    link_part = ""
    if recog is not None and persist is not None:
        if recog != persist:
            link_part = f"链数:{persist}≠识别{recog}"
        elif recog:
            link_part = f"链数:{recog}"

    tip = (base_tip or "").strip()
    if v.status == "structure_fail":
        reasons = v.hard_errors[:2]
        parts = ["不合格：结构", f"形态:{label}"]
        if link_part:
            parts.append(link_part)
        if reasons:
            parts.append("原因:" + "；".join(reasons))
        elif tip and not tip.startswith("成功") and not tip.startswith("待核"):
            parts.append(tip)
    elif v.status == "content_gap":
        parts = ["不合格：容量", f"形态:{label}"]
        if link_part:
            parts.append(link_part)
        # content_gap 的原因在 soft_warnings / hard 均可
        reasons = (v.hard_errors or [])[:2] or (v.soft_warnings or [])[:2]
        if reasons:
            parts.append("原因:" + "；".join(reasons))
    else:
        # 结构过硬门，但软提醒含【识别错误】→ 待核（勿与干净「成功」混在一起大海捞针）
        parse_soft = [
            w for w in (v.soft_warnings or []) if str(w).startswith("【识别错误】")
        ]
        missing_soft = [
            w for w in (v.soft_warnings or []) if str(w).startswith("【真没有】")
        ]
        if parse_soft:
            body = tip
            for pref in ("成功：", "成功", "待核："):
                if body.startswith(pref):
                    body = body[len(pref) :].lstrip("：: ").strip()
                    break
            head = f"待核：{body}" if body else "待核：识别存疑"
            parts = [head, f"形态:{label}"]
            if link_part:
                parts.append(link_part)
            parts.append("原因:" + "；".join(parse_soft[:2]))
        else:
            if tip.startswith("成功") or not tip:
                head = tip if tip.startswith("成功") else (tip or "成功：已提取主链")
            elif tip.startswith("待核"):
                head = tip
            else:
                head = tip if "成功" in tip else f"成功：{tip}"
            parts = [head, f"形态:{label}"]
            if link_part:
                parts.append(link_part)
            if missing_soft:
                parts.append("提醒:" + "；".join(missing_soft[:2]))

    return " · ".join(parts)[:280]


def warnings_from_frame(frame: ResourceFrame) -> list[str]:
    """给人看的中文列表：硬错误在前（已含【识别错误】/【真没有】）。"""
    return _uniq(list(frame.verdict.hard_errors) + list(frame.verdict.soft_warnings))
