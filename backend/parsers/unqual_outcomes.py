"""不合格种类：四类可确认 + 一类兜底待核。

可 100% 确认：
- 不合格：资源名 — 多资源未切开/不可区分
- 不合格：链接   — 链未进组/合计不一致；定型与实链不符
- 不合格：预览   — 帖有图却共享或未按名分配
- 不合格：容量   — 有容量声称却无可信大小或与帖面差过大

兜底（不能完全确认）：
- 不合格：待核 — 配额/V≠实链、预览截断、磁力无xl 等软存疑
  （旧文案「待核：…」归并于此）

旧文案「不合格：结构」按原因归并进前三类。
"""

from __future__ import annotations

UNQUAL_NAME = "不合格：资源名"
UNQUAL_LINK = "不合格：链接"
UNQUAL_PREVIEW = "不合格：预览"
UNQUAL_CAPACITY = "不合格：容量"
UNQUAL_REVIEW = "不合格：待核"

UNQUAL_KINDS = (
    UNQUAL_NAME,
    UNQUAL_LINK,
    UNQUAL_PREVIEW,
    UNQUAL_CAPACITY,
    UNQUAL_REVIEW,
)

# API / UI status key → 种类头
STATUS_TO_KIND = {
    "name": UNQUAL_NAME,
    "资源名": UNQUAL_NAME,
    "link": UNQUAL_LINK,
    "链接": UNQUAL_LINK,
    "preview": UNQUAL_PREVIEW,
    "预览": UNQUAL_PREVIEW,
    "capacity": UNQUAL_CAPACITY,
    "容量": UNQUAL_CAPACITY,
    "review": UNQUAL_REVIEW,
    "待核": UNQUAL_REVIEW,
    # 旧筛选兼容
    "structure": UNQUAL_NAME,
    "结构": UNQUAL_NAME,
}

KIND_TO_STATUS = {
    UNQUAL_NAME: "name",
    UNQUAL_LINK: "link",
    UNQUAL_PREVIEW: "preview",
    UNQUAL_CAPACITY: "capacity",
    UNQUAL_REVIEW: "review",
}

_PREVIEW_KW = ("预览", "配图", "首图", "分开配图")
_LINK_KW = (
    "链数不合规",
    "漏链",
    "下载链",
    "未进组",
    "链形态不一致",
    "定型为",
    "填出多条链",
    "出现多链",
)
_NAME_KW = (
    "资源名",
    "片名",
    "未切开",
    "漏切",
    "等于帖标题",
    "重复资源名",
    "名称标签",
    "标题写×",
    "标题写x",
    "实际入库",
    "只填出",
    "子名",
)
_CAP_KW = ("容量", "大小为0", "写出了大小", "各子资源", "总容量", "入库资源写", "入库大小")


def classify_unqual_kind(
    *,
    status: str = "",
    errors: list[str] | None = None,
    outcome: str = "",
) -> str:
    """由验收 status + 原因文案判定合并种类。"""
    blob = "；".join(str(x) for x in (errors or []) if x)
    out = (outcome or "").strip()
    if not blob and out:
        if "原因:" in out:
            blob = out.split("原因:", 1)[-1]
        elif "原因：" in out:
            blob = out.split("原因：", 1)[-1]
        else:
            blob = out

    st = (status or "").strip().lower()
    # 人工已审前缀不影响原不合格归类
    if out.startswith("人工已审 · "):
        out = out[len("人工已审 · ") :].strip()
    for kind in UNQUAL_KINDS:
        if out.startswith(kind):
            return kind
    # 旧「待核：」前缀 → 兜底
    if out.startswith("待核：") or out.startswith("待核:"):
        return UNQUAL_REVIEW
    if st in {"review", "待核"}:
        return UNQUAL_REVIEW

    if st in {"content_gap", "capacity"} or out.startswith(UNQUAL_CAPACITY) or out.startswith(
        "不合格：容量"
    ):
        return UNQUAL_CAPACITY
    if blob and any(k in blob for k in _CAP_KW) and not any(
        k in blob for k in _NAME_KW + _LINK_KW + _PREVIEW_KW
    ):
        return UNQUAL_CAPACITY

    # 硬错归类：预览 > 链接 > 资源名
    if any(k in blob for k in _PREVIEW_KW):
        return UNQUAL_PREVIEW
    if any(k in blob for k in _LINK_KW):
        return UNQUAL_LINK
    if any(k in blob for k in _NAME_KW):
        return UNQUAL_NAME
    if any(k in blob for k in _CAP_KW):
        return UNQUAL_CAPACITY

    if out.startswith("不合格：结构") or st == "structure_fail":
        return UNQUAL_NAME
    if out.startswith("不合格：容量"):
        return UNQUAL_CAPACITY
    return UNQUAL_NAME


def normalize_unqual_reason_kind(reason_or_outcome: str) -> str:
    """下拉/列表归并：新旧 outcome → 五类之一。"""
    r = (reason_or_outcome or "").strip()
    if not r:
        return r
    return classify_unqual_kind(outcome=r)
