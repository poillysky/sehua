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

from parsers.boards import DISCUZ_BOARD_FID, get_board_policy, parse_board_key
from parsers.links import DualParseResult, parse_thread_dual
from parsers.list_dates import extract_thread_posted_at, is_thread_old_enough
from parsers.thread_gates import (
    has_115_sha_link,
    has_baidu_share_link,
    has_115_share_link,
    has_pikpak_share_link,
    has_target_link,
    has_xunlei_share_link,
    is_genuine_non_resource,
    is_non_target_cloud_share,
    is_purchase_required_post,
    is_reply_required_post,
    is_safe_or_soft_shell,
    is_thread_access_denied,
    is_thread_author_banned,
    is_thread_login_required,
    is_thread_moderator_blocked,
    looks_like_attachment_zone,
    is_missing_thread,
    page_title,
    post_text,
    should_skip_as_115sha_only,
    thread_typeid_mismatch,
    title_implies_resource,
    title_is_115sha_without_ed2k_magnet,
    title_is_baidu_pan_without_ed2k_magnet,
    title_is_pikpak_without_ed2k_magnet,
    title_is_xunlei_cloud_without_ed2k_magnet,
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
    # 兼容子版 key「141:689」：龄期/主链偏好必须落到正确策略
    pol = get_board_policy(board_fid)
    fid = int(pol.fid or 0) or parse_board_key(board_fid)[0]
    link_kind = (preferred_link or (pol.primary_link if pol else "magnet") or "magnet").strip().lower()
    if link_kind not in {"magnet", "ed2k", "both"}:
        link_kind = "magnet"
    # 仅综合讨论区(fid=95)限制 typeid=716 情色分享；其它板块不做分类限制
    # 解析测试「双链」模式不套用分类硬跳过，避免误判磁力帖
    required_typeid = (
        pol.list_typeid if pol and fid == DISCUZ_BOARD_FID and link_kind != "both" else None
    )
    min_age = int(getattr(pol, "min_thread_age_days", 0) or 0)

    page_tit = page_title(html)
    # 展示用：页内伪标题时回落到列表标题；无权占位也可用列表标题登记
    title = page_tit
    if not title_recognizable(title) and title_recognizable(list_title):
        title = list_title
    # 与 parse_thread_dual 对齐：目标链/网盘/跳过一律只认楼主语料，忽略回帖
    try:
        from parsers.content import extract_link_corpus_html

        link_corpus = extract_link_corpus_html(html) or ""
    except Exception:
        link_corpus = ""
    text = post_text(html) or link_corpus
    if not link_corpus:
        link_corpus = text
    has_lz_target = has_target_link(link_corpus, link_kind)

    # 软文 / 安全壳优先（真帖有一楼正文时不会误进这里）
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

    # 帖子已删 / tid 无效：明确跳过（勿落成「非资源帖」）
    if is_missing_thread(html, page_tit):
        return ThreadOutcome("skipped", "帖子不存在（跳过）", link_kind, title)

    # 版主/管理员屏蔽：内容不可见，直接跳过（不占位、不重试）
    if is_thread_moderator_blocked(html):
        return ThreadOutcome("skipped", "版主屏蔽（跳过）", link_kind, title)
    # 作者被禁/删：正文自动屏蔽，直接跳过
    if is_thread_author_banned(html):
        return ThreadOutcome("skipped", "作者已禁止（跳过）", link_kind, title)

    if is_thread_access_denied(html):
        # 页内真标题优先；伪标题（提示信息）时用列表/标题列登记占位，供账号爬
        if title_recognizable(page_tit):
            return ThreadOutcome("stub", "无阅读权限 · 占位入库", link_kind, page_tit)
        if title_recognizable(list_title):
            return ThreadOutcome("stub", "无阅读权限 · 占位入库", link_kind, list_title.strip())
        return ThreadOutcome(
            "skipped",
            "无阅读权限（无有效标题，跳过）",
            link_kind,
            page_tit or list_title or title,
        )

    # 龄期板（网友原创区等）：未满龄一律跳过，不占位、不抓附件
    if min_age > 0:
        posted_at = extract_thread_posted_at(html)
        if posted_at is not None and not is_thread_old_enough(
            posted_at, min_age_days=min_age
        ):
            return ThreadOutcome(
                "skipped",
                f"未满 {min_age} 天（跳过）",
                link_kind,
                title,
            )

    # 115sha 直链：只认楼主语料；已有 magnet/ed2k 不跳；有附件区则先下附件
    if has_115_sha_link(link_corpus):
        if should_skip_as_115sha_only(link_corpus):
            has_attach_corpus = "postmessage_attach" in (html or "")
            if not attachments_already_tried and looks_like_attachment_zone(html):
                pass  # 先下附件
            elif attachments_already_tried and not has_attach_corpus:
                # 附件已试但未注入（解压失败/空包）：勿把正文 115 目录误标成「附件跳过」
                pass
            else:
                tip = (
                    "115sha 链接（附件，跳过）"
                    if has_attach_corpus
                    else "115sha 链接（跳过）"
                )
                return ThreadOutcome("skipped", tip, link_kind, title)
        # 已有目标链：继续走正文导入 / 附件逻辑

    # 115 网盘分享页：有分享链则走正文解析入库（见 parse_thread_dual），不再跳过。
    # 仍跳过：仅标题写 115 分享、正文无实际链接（见下方 title 分支已移除分享标题硬跳）。

    # 迅雷 / PikPak / 百度：只看楼主语料（勿扫回帖广告链）；无目标链且无附件可试时才跳过
    if has_xunlei_share_link(link_corpus) and not has_lz_target:
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "迅雷云盘（跳过）", link_kind, title)

    if has_pikpak_share_link(link_corpus) and not has_lz_target:
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "PikPak网盘（跳过）", link_kind, title)

    if has_baidu_share_link(link_corpus) and not has_lz_target:
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "百度网盘（跳过）", link_kind, title)

    # 标题仅 115sha / 迅雷 / PikPak / 百度、且正文无目标链：
    # 115sha 标题若带附件区，先下附件（常见：标题写 115sha1，rar 内实为 ed2k）
    # （正文已有 115cdn 分享 / ed2k / 磁力时不因标题里的「百度」等字样硬跳）
    if title_is_115sha_without_ed2k_magnet(title) or title_is_115sha_without_ed2k_magnet(
        list_title
    ):
        if has_lz_target:
            pass
        elif has_115_share_link(link_corpus):
            # 标题写 115sha1，正文实为 115.com/s/ 分享码 → 入库
            pass
        elif not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "115sha 标题（无 ed2k/磁力，跳过）", link_kind, title)
    _has_body_target = has_lz_target
    if not _has_body_target and (
        title_is_xunlei_cloud_without_ed2k_magnet(title)
        or title_is_xunlei_cloud_without_ed2k_magnet(list_title)
    ):
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "迅雷云盘标题（无 ed2k/磁力，跳过）", link_kind, title)
    if not _has_body_target and (
        title_is_pikpak_without_ed2k_magnet(title)
        or title_is_pikpak_without_ed2k_magnet(list_title)
    ):
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "PikPak标题（无 ed2k/磁力，跳过）", link_kind, title)
    if not _has_body_target and (
        title_is_baidu_pan_without_ed2k_magnet(title)
        or title_is_baidu_pan_without_ed2k_magnet(list_title)
    ):
        if not attachments_already_tried and looks_like_attachment_zone(html):
            pass
        else:
            return ThreadOutcome("skipped", "百度网盘标题（无 ed2k/磁力，跳过）", link_kind, title)

    # 需回复：满龄（或非龄期板）→ 占位显示；未满龄已在上一步跳过
    if is_reply_required_post(html):
        return ThreadOutcome("stub", "需回复贴", link_kind, title)
    if is_purchase_required_post(html):
        return ThreadOutcome("stub", "需购买贴", link_kind, title)

    # Body has target link? 仅认楼主语料（与 parse_thread_dual 一致）
    # 回帖/侧栏误检到的链不走进「有链但无主资源」失败。
    if has_lz_target:
        parsed = parse_thread_dual(
            html,
            tid=0,
            preferred_link=link_kind,
            base_url=base_url,
            board_fid=board_fid,
        )  # type: ignore[arg-type]
        if parsed.primary_link_kind != "none" and parsed.assets:
            # 报表用实际主链类型（含：磁力板仅有 115 分享码 → 115share）
            outcome_kind = parsed.primary_link_kind
            return ThreadOutcome(
                "import",
                (
                    "成功：正文含115分享码"
                    if outcome_kind == "115share"
                    else "成功：正文含目标链接"
                ),
                outcome_kind,
                parsed.title or title,
                parsed=parsed,
            )
        # 楼主语料检出目标链形态但解析无主资源：
        # 实为网盘 → 跳过；有附件区 → 继续下附件；否则失败。
        if not attachments_already_tried and not looks_like_attachment_zone(html):
            if is_non_target_cloud_share(link_kind=link_kind, text=link_corpus):
                return ThreadOutcome(
                    "skipped", "非ED2K资源（网盘分享）", link_kind, title
                )
            if (
                has_baidu_share_link(link_corpus)
                or has_xunlei_share_link(link_corpus)
                or has_pikpak_share_link(link_corpus)
            ):
                tip = (
                    "百度网盘（跳过）"
                    if has_baidu_share_link(link_corpus)
                    else (
                        "迅雷云盘（跳过）"
                        if has_xunlei_share_link(link_corpus)
                        else "PikPak网盘（跳过）"
                    )
                )
                return ThreadOutcome("skipped", tip, link_kind, title)
            return ThreadOutcome("failed", "解析入库失败（有链但无主资源）", link_kind, title)

    # No usable body link yet — attachment strategy (ed2k-aligned)
    if not attachments_already_tried and looks_like_attachment_zone(html):
        if link_kind in {"magnet", "both"}:
            from parsers.attachments import pick_magnet_attachment_kind

            attach_kind = pick_magnet_attachment_kind(base_url or "", html)
            return ThreadOutcome(
                "need_attachments",
                (
                    "正文无磁力，尝试 Excel/文本附件"
                    if attach_kind == "txt_tail"
                    else (
                        "正文无磁力，尝试种子附件"
                        if link_kind == "magnet"
                        else "正文无链，尝试种子附件"
                    )
                ),
                link_kind,
                title,
                need_attachments=True,
                attachment_kind=attach_kind,
            )
        if link_kind == "ed2k":
            from parsers.attachments import pick_ed2k_attachment_kind

            attach_kind = pick_ed2k_attachment_kind(base_url or "", html)
            return ThreadOutcome(
                "need_attachments",
                (
                    "正文无电驴/磁力，尝试种子附件转磁力"
                    if attach_kind == "torrent"
                    else "正文无电驴/磁力，尝试尾部 txt/压缩包/Excel 附件"
                ),
                link_kind,
                title,
                need_attachments=True,
                attachment_kind=attach_kind,
            )

    if attachment_denied:
        return ThreadOutcome("stub", "无权限下载附件", link_kind, title)
    if attachment_failed:
        return ThreadOutcome("retry", "附件下载失败，待重试", link_kind, title)
    # 附件已下载/已尝试，但抽不出 ed2k/磁力 → 跳过（勿占位；无权才走上方 stub）
    if had_attachments or attachments_already_tried:
        return ThreadOutcome(
            "skipped",
            "未解析到 ed2k/磁力（跳过）",
            link_kind,
            title,
        )

    if is_non_target_cloud_share(link_kind=link_kind, text=link_corpus) and not title_implies_resource(
        title, link_kind
    ):
        return ThreadOutcome("skipped", "非ED2K资源（网盘分享）", link_kind, title)

    wrong_typeid = bool(
        required_typeid
        and fid == DISCUZ_BOARD_FID
        and thread_typeid_mismatch(html, str(fid), required_typeid)
    )
    if is_genuine_non_resource(html=html, title=title, link_kind=link_kind, text=link_corpus):
        outcome = (
            "非情色分享分类"
            if wrong_typeid
            else "非资源帖（无目标链接）"
        )
        return ThreadOutcome("skipped", outcome, link_kind, title)

    if wrong_typeid:
        return ThreadOutcome("retry", "非情色分享分类，待复核", link_kind, title)
    # 正文/附件均无 ed2k、magnet → 跳过（含标题暗示资源）
    if title_implies_resource(title, link_kind):
        return ThreadOutcome("skipped", "未解析到 ed2k/磁力（跳过）", link_kind, title)
    if len(html or "") < 8000:
        return ThreadOutcome("retry", "页面过短/未正常加载", link_kind, title)

    return ThreadOutcome("skipped", "未发现 ed2k/磁力链接（跳过）", link_kind, title)
