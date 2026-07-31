"""附件触发：切块+卡片+试算之后，再决定要不要下、怎么停。

口径：
- 单资源：正文无链 / 试算「不合格」（含额度不匹配）→ 下；额度/试算合格 → 停
- 多资源：某块缺链或整帖试算不合格 → 下；不做额度匹配停手，目标认全链
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from parsers.attachments import AttachmentFetchResult
from parsers.links import DualParseResult
from parsers.skip_outcomes import (
    RETRY_ATTACH_FAILED,
    SKIP_ATTACH_EMPTY,
    STUB_ATTACH_DENIED,
)
from parsers.thread_gates import looks_like_attachment_zone
from workers.thread_outcome import ThreadOutcome

ResourceMode = Literal["single", "multi"]
AttachMode = Literal["no_link", "single_unqual", "multi_missing"]


def outcome_from_attach_rejudge_failure(
    attach_res: AttachmentFetchResult,
    *,
    link_kind: str,
    title: str,
) -> ThreadOutcome | None:
    """正文残链复判：附件侧结果优先于正文「待核/漏链」。

    优先级（高→低）：
      1. 无权 / 需登录 → stub「附件无权（占位入库）」
      2. 空附件 / 空种子 → skipped
      3. 下载失败 / 无可用语料 → retry「附件下载失败」
    返回 None：已有可入库附件语料，交给合并复判。
    """
    tip_title = (title or "").strip()
    kind = (link_kind or "magnet").strip() or "magnet"
    text = str(getattr(attach_res, "text", "") or "").strip()
    # 已抽到可入库链：上层 download_tail 会清掉 denied；此处双保险
    if text:
        low = text.lower()
        if "ed2k://" in low or "magnet:?" in low:
            return None
    if attach_res.denied or bool(getattr(attach_res, "login_required", False)):
        return ThreadOutcome("stub", STUB_ATTACH_DENIED, kind, tip_title)
    if bool(getattr(attach_res, "empty_attachment", False)):
        return ThreadOutcome("skipped", SKIP_ATTACH_EMPTY, kind, tip_title)
    if bool(getattr(attach_res, "empty_torrent", False)):
        return ThreadOutcome("skipped", "种子大小为0", kind, tip_title)
    if (
        attach_res.failed
        or not attach_res.downloaded
        or not text
    ):
        return ThreadOutcome("retry", RETRY_ATTACH_FAILED, kind, tip_title)
    return None


@dataclass(slots=True)
class AttachPlan:
    should_fetch: bool
    mode: AttachMode
    attachment_kind: str
    # 单资源：标题 N配额未齐也继续；多资源：关闭配额停手
    quota_stop: bool
    # 无链先下：日限入队；正文复判：日限也优先报附件侧，不闷留正文待核
    queue_on_daily_limit: bool
    reason: str


def classify_resource_mode(
    parsed: DualParseResult | None,
    html: str,
    *,
    post_title: str = "",
) -> ResourceMode:
    """≤1 名称标签 / 单组 frame → single；≥2 → multi。"""
    from parsers.content import first_floor_name_label_count

    if first_floor_name_label_count(html) >= 2:
        return "multi"
    if parsed is None or not parsed.assets:
        return "single"
    try:
        from db.persist import build_parse_frame

        frame = build_parse_frame(parsed, post_title=post_title or "")
        if frame is not None and len(getattr(frame, "rows", []) or []) >= 2:
            return "multi"
    except Exception:
        pass
    return "single"


def frame_has_missing_block_links(
    parsed: DualParseResult,
    *,
    post_title: str = "",
) -> bool:
    """多资源任一组无下载链。"""
    try:
        from db.persist import build_parse_frame

        frame = build_parse_frame(parsed, post_title=post_title or "")
        if frame is None:
            return False
        rows = getattr(frame, "rows", None) or []
        if len(rows) < 2:
            return False
        return any(not (getattr(r, "links", None) or []) for r in rows)
    except Exception:
        return False


def _pick_kind(thread_url: str, html: str, link_pref: str, title: str) -> str:
    from parsers.attachments import pick_ed2k_attachment_kind, pick_magnet_attachment_kind

    if (link_pref or "").strip().lower() == "ed2k":
        return pick_ed2k_attachment_kind(thread_url, html)
    return pick_magnet_attachment_kind(thread_url, html, title=title or "")


def plan_attachment_fetch(
    *,
    parsed: DualParseResult,
    html: str,
    outcome: ThreadOutcome,
    attach_tried: bool,
    link_pref: str,
    thread_url: str,
    list_title: str = "",
    persist: bool = True,
    pending_need_attach: bool = False,
    pending_kind: str = "",
) -> AttachPlan | None:
    """切块卡片后的附件计划；None=不下。"""
    if attach_tried:
        return None
    if not looks_like_attachment_zone(html):
        return None

    tip = str(outcome.outcome or "")
    if outcome.verdict == "stub" and tip.startswith("0元购买"):
        return None
    if outcome.verdict in {"skipped", "failed", "retry", "stub"} and not pending_need_attach:
        return None

    title = str(outcome.title or list_title or getattr(parsed, "title", "") or "")
    res_mode = classify_resource_mode(parsed, html, post_title=title)
    kind = (pending_kind or outcome.attachment_kind or "").strip()
    if not kind:
        kind = _pick_kind(thread_url, html, link_pref, title)

    # 正文无链：judge 已标 need_attachments，切块后再下
    if pending_need_attach or outcome.verdict == "need_attachments":
        return AttachPlan(
            should_fetch=True,
            mode="no_link",
            attachment_kind=kind,
            quota_stop=(res_mode == "single"),
            queue_on_daily_limit=True,
            reason="正文无有效链，切块后下附件",
        )

    if outcome.verdict != "import":
        return None
    # 正文有链复判：与历史一致，仅持久化路径触发（探测可不下）
    if not persist:
        return None

    from db.persist import preview_frame_outcome

    preview = preview_frame_outcome(
        parsed, import_outcome=str(outcome.outcome or ""), post_title=title
    )

    if res_mode == "multi":
        missing = frame_has_missing_block_links(parsed, post_title=title)
        if missing or (preview or "").startswith("不合格"):
            return AttachPlan(
                should_fetch=True,
                mode="multi_missing",
                attachment_kind=kind,
                quota_stop=False,
                queue_on_daily_limit=False,
                reason=(
                    "多资源块缺链"
                    if missing
                    else f"多资源试算不合格:{(preview or '')[:40]}"
                ),
            )
        return None

    # 单资源
    if not parsed.assets:
        return AttachPlan(
            should_fetch=True,
            mode="no_link",
            attachment_kind=kind,
            quota_stop=True,
            queue_on_daily_limit=True,
            reason="单资源切块后仍无链",
        )
    if (preview or "").startswith("不合格"):
        return AttachPlan(
            should_fetch=True,
            mode="single_unqual",
            attachment_kind=kind,
            quota_stop=True,
            queue_on_daily_limit=False,
            reason=f"单资源试算不合格:{(preview or '')[:40]}",
        )
    return None
