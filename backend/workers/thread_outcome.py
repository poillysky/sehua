"""Single-thread outcome judge — aligned with ed2k detail_spider / thread_import_judge.

Outcomes:
- import   正常入库（有板块目标主链）
- stub     占位入库 unavailable://thread/...
- skipped  战略跳过，不再处理
- failed   永久失败（有链但入库 0）
- retry    保留待重试（本轮不写或可稍后）
- need_attachments  需先下附件再解析（调用方负责下载后重判）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from parsers.boards import DISCUZ_BOARD_FID, get_board_policy
from parsers.links import DualParseResult, parse_thread_dual
from parsers.thread_gates import (
    has_target_link,
    is_genuine_non_resource,
    is_non_target_cloud_share,
    is_purchase_required_post,
    is_reply_required_post,
    is_safe_or_soft_shell,
    is_thread_access_denied,
    is_thread_login_required,
    looks_like_attachment_zone,
    page_title,
    post_text,
    thread_typeid_mismatch,
    title_implies_resource,
    title_recognizable,
)

Verdict = Literal["import", "stub", "skipped", "failed", "retry", "need_attachments"]

VERDICT_LABELS: dict[str, str] = {
    "import": "正常入库",
    "stub": "占位入库",
    "skipped": "跳过",
    "failed": "失败",
    "retry": "保留重试",
    "need_attachments": "需下附件再解析",
}


@dataclass(slots=True)
class ThreadOutcome:
    verdict: Verdict
    outcome: str
    link_kind: str
    title: str
    need_attachments: bool = False
    attachment_kind: str = ""  # torrent | txt_tail | ""
    need_browser_retry: bool = False  # 软文/壳：应用浏览器整页重读
    soft_browser_retried: bool = False
    parsed: DualParseResult | None = None

    @property
    def label(self) -> str:
        return VERDICT_LABELS.get(self.verdict, self.verdict)


def judge_thread_html(
    html: str,
    *,
    board_fid: int | str,
    list_title: str = "",
    base_url: str = "",
    attachment_denied: bool = False,
    attachment_failed: bool = False,
    had_attachments: bool = False,
    attachments_already_tried: bool = False,
    soft_browser_retried: bool = False,
    preferred_link: str | None = None,
) -> ThreadOutcome:
    """Pure judgment from HTML (+ optional attachment attempt flags).

    preferred_link: 覆盖板块主链偏好；解析测试留空板块时传 \"both\"。
    """
    fid = int(board_fid) if str(board_fid).isdigit() else 0
    pol = get_board_policy(fid) if fid else None
    link_kind = (preferred_link or (pol.primary_link if pol else "magnet") or "magnet").strip().lower()
    if link_kind not in {"magnet", "ed2k", "both"}:
        link_kind = "magnet"
    # 仅综合讨论区(fid=95)限制 typeid=716 情色分享；其它板块不做分类限制
    # 解析测试「双链」模式不套用分类硬跳过，避免误判磁力帖
    required_typeid = (
        pol.list_typeid if pol and fid == DISCUZ_BOARD_FID and link_kind != "both" else None
    )

    page_tit = page_title(html)
    # 列表标题仅作展示补全；登录/无权页判定必须用页内标题，避免「提示信息」被列表名抬成可占位
    title = page_tit
    if not title_recognizable(title) and title_recognizable(list_title):
        title = list_title
    text = post_text(html)

    if is_safe_or_soft_shell(html):
        if soft_browser_retried:
            return ThreadOutcome(
                "retry",
                "软文浏览器重试后仍失败，保留待下轮",
                link_kind,
                title,
                soft_browser_retried=True,
            )
        return ThreadOutcome(
            "retry",
            "站点软文/安全壳，改用浏览器整页重试",
            link_kind,
            title,
            need_browser_retry=True,
        )

    if is_thread_login_required(html):
        if title_recognizable(page_tit):
            return ThreadOutcome("stub", "帖子需论坛登录", link_kind, page_tit)
        return ThreadOutcome("skipped", "帖子需论坛登录（无有效标题）", link_kind, page_tit or title)

    if is_thread_access_denied(html):
        # 页内真标题可占位出队；「提示信息」等伪标题直接跳过，不用列表标题凑数
        if title_recognizable(page_tit):
            return ThreadOutcome("stub", "无阅读权限 · 占位入库", link_kind, page_tit)
        return ThreadOutcome(
            "skipped",
            "无阅读权限（非正常标题，跳过）",
            link_kind,
            page_tit or title,
        )

    # Body has target link?
    if has_target_link(text, link_kind) or has_target_link(html, link_kind):
        parsed = parse_thread_dual(
            html,
            tid=0,
            preferred_link=link_kind,
            base_url=base_url,
            board_fid=board_fid,
        )  # type: ignore[arg-type]
        if parsed.primary_link_kind != "none" and parsed.assets:
            # ed2k 板若只有磁力，primary 为 magnet；报表用实际主链类型
            outcome_kind = (
                parsed.primary_link_kind
                if link_kind in {"both", "ed2k"}
                else link_kind
            )
            return ThreadOutcome(
                "import",
                "成功：正文含目标链接",
                outcome_kind,
                parsed.title or title,
                parsed=parsed,
            )
        return ThreadOutcome("failed", "解析入库失败（有链但无主资源）", link_kind, title)

    # No target link yet — attachment strategy (ed2k-aligned)
    if not attachments_already_tried and looks_like_attachment_zone(html):
        if link_kind in {"magnet", "both"}:
            return ThreadOutcome(
                "need_attachments",
                "正文无磁力，尝试种子附件" if link_kind == "magnet" else "正文无链，尝试种子附件",
                link_kind,
                title,
                need_attachments=True,
                attachment_kind="torrent",
            )
        if link_kind == "ed2k":
            if is_reply_required_post(html):
                return ThreadOutcome("stub", "需回复贴", link_kind, title)
            return ThreadOutcome(
                "need_attachments",
                "正文无电驴/磁力，尝试尾部 txt/压缩包附件",
                link_kind,
                title,
                need_attachments=True,
                attachment_kind="txt_tail",
            )

    if is_reply_required_post(html):
        return ThreadOutcome("stub", "需回复贴", link_kind, title)
    if is_purchase_required_post(html):
        return ThreadOutcome("stub", "需购买贴", link_kind, title)
    if attachment_denied:
        return ThreadOutcome("stub", "无权限下载附件", link_kind, title)
    if attachment_failed:
        return ThreadOutcome("retry", "附件下载失败，待重试", link_kind, title)
    if had_attachments:
        return ThreadOutcome("retry", "附件未解析出链接，待重试", link_kind, title)

    if is_non_target_cloud_share(link_kind=link_kind, text=text) and not title_implies_resource(
        title, link_kind
    ):
        return ThreadOutcome("skipped", "非ED2K资源（网盘分享）", link_kind, title)

    wrong_typeid = bool(
        required_typeid
        and fid == DISCUZ_BOARD_FID
        and thread_typeid_mismatch(html, str(fid), required_typeid)
    )
    if is_genuine_non_resource(html=html, title=title, link_kind=link_kind, text=text):
        outcome = (
            "非情色分享分类"
            if wrong_typeid
            else "非资源帖（无目标链接）"
        )
        return ThreadOutcome("skipped", outcome, link_kind, title)

    if wrong_typeid:
        return ThreadOutcome("retry", "非情色分享分类，待复核", link_kind, title)
    if title_implies_resource(title, link_kind):
        return ThreadOutcome("retry", "标题暗示有资源但未解析到链接", link_kind, title)
    if len(html or "") < 8000:
        return ThreadOutcome("retry", "页面过短/未正常加载", link_kind, title)

    return ThreadOutcome("retry", "未发现资源链接，待重试", link_kind, title)
