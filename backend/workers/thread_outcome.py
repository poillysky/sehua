"""Single-thread outcome judge — aligned with ed2k detail_spider / thread_import_judge.

Outcomes:
- import   正常入库（有板块目标主链）
- stub     占位入库 unavailable://thread/...
- skipped  已见正文，战略跳过不再入库（网盘/115sha/非资源/无链等）
- failed   未见到正文就出队（抓取/软文壳/拦截重试耗尽）——不进帖子识别
- retry    保留待重试（本轮不写或可稍后；含暂时看不见正文）
- need_attachments  需先下附件再解析（调用方负责下载后重判）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from parsers.boards import DISCUZ_BOARD_FID, parse_board_key
from parsers.links import DualParseResult, parse_thread_dual
from parsers.list_dates import extract_thread_posted_at, is_thread_old_enough
from parsers.skip_outcomes import (
    SKIP_115SHA,
    SKIP_AUTHOR_BANNED,
    SKIP_LOGIN_NO_TITLE,
    SKIP_META_AD,
    SKIP_MISSING,
    SKIP_MOD_BLOCKED,
    SKIP_NO_ACCESS_NO_TITLE,
    SKIP_NO_TARGET,
    SKIP_NON_RESOURCE,
    SKIP_PURCHASE,
    age_skip_tip,
)
from parsers.thread_gates import (
    has_115_sha_link,
    has_115_share_link,
    has_target_link,
    is_genuine_non_resource,
    is_non_target_cloud_share,
    is_free_purchase_post,
    is_purchase_required_post,
    is_reply_required_post,
    is_safe_or_soft_shell,
    is_thread_access_denied,
    is_thread_author_banned,
    is_thread_login_required,
    is_thread_moderator_blocked,
    looks_like_attachment_zone,
    is_empty_tip_page,
    is_missing_thread,
    match_skip_cloud_share_link,
    match_skip_cloud_share_title,
    page_title,
    post_text,
    should_skip_as_115sha_only,
    thread_typeid_mismatch,
    title_has_target_or_115_hint,
    title_implies_resource,
    title_is_115sha_without_ed2k_magnet,
    title_recognizable,
    coalesce_thread_title,
)

Verdict = Literal["import", "stub", "skipped", "failed", "retry", "need_attachments"]

VERDICT_LABELS: dict[str, str] = {
    "import": "正常入库",
    "stub": "占位入库",
    "skipped": "跳过",
    "failed": "失败（未见正文）",
    "retry": "保留重试",
    "need_attachments": "需下附件再解析",
}


def _is_body_sample_ed2k(uri: str, *, size: int = 0) -> bool:
    """正文里的附件样例链（*_ss.rar / 小体积 rar），不当作「多资源结构化正文」。"""
    u = uri or ""
    if re.search(r"_ss\.rar", u, re.I):
        return True
    if size > 0 and size < 100 * 1024 * 1024 and re.search(r"\.rar\|", u, re.I):
        return True
    if re.search(r"预览|樣例|样例", u):
        return True
    return False


def _body_has_multi_structured_targets(link_corpus: str, *, link_kind: str) -> bool:
    """多资源结构化正文：≥2 独立目标链 + 种子名/子标题标签。

    用于附件无权占位等：合集正文已切开时勿因附件失败改 stub。
    """
    text = link_corpus or ""
    if not text.strip():
        return False
    kind = (link_kind or "magnet").strip().lower()
    n_links = 0
    if kind in {"magnet", "both"}:
        from parsers.magnet import parse_magnet_text

        n_links = max(n_links, len({m.infohash for m in parse_magnet_text(text)}))
    if kind in {"ed2k", "both"}:
        from parsers.ed2k import parse_ed2k_text

        try:
            real = []
            for x in parse_ed2k_text(text):
                if not x.hash:
                    continue
                if _is_body_sample_ed2k(x.link or "", size=int(x.size or 0)):
                    continue
                real.append(x.hash)
            n_links = max(n_links, len(set(real)))
        except Exception:
            pass
    if n_links < 2:
        return False
    seed_n = len(
        re.findall(r"【\s*种子名称|【\s*種子名稱|【\s*种子名稱|【\s*種子名称", text)
    )
    if seed_n >= 2:
        return True
    try:
        from parsers.content import iter_size_field_spans, iter_subresource_title_spans

        if len(iter_subresource_title_spans(text)) >= 2:
            return True
        # 2048 国产合集常见：多段【影片大小】+ 多磁力，无【影片名称】标签
        if len(iter_size_field_spans(text)) >= 2:
            return True
    except Exception:
        pass
    return False


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
    attachment_login_required: bool = False,
    attachment_failed: bool = False,
    attachment_empty_torrent: bool = False,
    had_attachments: bool = False,
    attachments_already_tried: bool = False,
    soft_browser_retried: bool = False,
    preferred_link: str | None = None,
    forum_id: str = "sehuatang",
    tid: int | None = None,
) -> ThreadOutcome:
    """Pure judgment from HTML (+ optional attachment attempt flags).

    preferred_link: 覆盖板块主链偏好；解析测试留空板块时传 \"both\"。
    """
    from crawler.sites import get_site_adapter

    # 兼容子版 key「141:689」：龄期/主链偏好必须落到正确策略
    adapter = get_site_adapter(forum_id)
    pol = adapter.get_board_policy(board_fid)
    fid = int(pol.fid or 0) or parse_board_key(board_fid)[0]
    link_kind = (preferred_link or (pol.primary_link if pol else "magnet") or "magnet").strip().lower()
    if link_kind not in {"magnet", "ed2k", "both"}:
        link_kind = "magnet"
    # 仅色花堂综合讨论区(fid=95)限制 typeid=716 情色分享；其它板块/论坛不做分类限制
    # 解析测试「双链」模式不套用分类硬跳过，避免误判磁力帖
    required_typeid = (
        pol.list_typeid
        if pol and forum_id == "sehuatang" and fid == DISCUZ_BOARD_FID and link_kind != "both"
        else None
    )
    min_age = int(getattr(pol, "min_thread_age_days", 0) or 0)

    page_tit = page_title(html)
    # 展示用标题：只认列表扫描；列表空/伪标题才用帖页
    title = coalesce_thread_title(list_title, page_tit) or (
        (list_title or "").strip() or page_tit or ""
    )

    # 2048 白名单各板：回家指南 / 来访者必看 / 地址发布器等版务帖
    if forum_id == "2048":
        from parsers.boards_2048 import is_2048_meta_guide_thread

        if (
            is_2048_meta_guide_thread(title or "", tid)
            or is_2048_meta_guide_thread(list_title or "", tid)
        ):
            return ThreadOutcome(
                "skipped", SKIP_META_AD, link_kind, title or list_title
            )

    # 与 parse_thread_dual 对齐：目标链/网盘/跳过一律只认主贴语料，忽略回帖
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
        if title_recognizable(list_title):
            return ThreadOutcome("stub", "帖子需论坛登录", link_kind, list_title.strip())
        if title_recognizable(page_tit):
            return ThreadOutcome("stub", "帖子需论坛登录", link_kind, page_tit)
        return ThreadOutcome(
            "skipped",
            SKIP_LOGIN_NO_TITLE,
            link_kind,
            list_title or page_tit or title,
        )

    # 空提示页（限流/临时错误）：先浏览器整页重读；仍空再进退避队列
    if is_empty_tip_page(html):
        if soft_browser_retried:
            return ThreadOutcome(
                "retry",
                "提示页无正文，待重试",
                link_kind,
                title,
                soft_browser_retried=True,
            )
        return ThreadOutcome(
            "retry",
            "提示页无正文，改用浏览器整页重试",
            link_kind,
            title,
            need_browser_retry=True,
        )

    # 帖子已删 / tid 无效：明确跳过（勿落成「非资源」）
    if is_missing_thread(html, page_tit):
        return ThreadOutcome("skipped", SKIP_MISSING, link_kind, title)

    # 版主/管理员屏蔽：内容不可见，直接跳过（不占位、不重试）
    if is_thread_moderator_blocked(html):
        return ThreadOutcome("skipped", SKIP_MOD_BLOCKED, link_kind, title)
    # 作者被禁/删：正文自动屏蔽，直接跳过
    if is_thread_author_banned(html):
        return ThreadOutcome("skipped", SKIP_AUTHOR_BANNED, link_kind, title)

    if is_thread_access_denied(html):
        # 无权页标题几乎总是「提示信息」：优先用列表标题占位入库
        if title_recognizable(list_title):
            return ThreadOutcome(
                "stub", "无阅读权限 · 占位入库", link_kind, list_title.strip()
            )
        if title_recognizable(page_tit):
            return ThreadOutcome("stub", "无阅读权限 · 占位入库", link_kind, page_tit)
        return ThreadOutcome(
            "skipped",
            SKIP_NO_ACCESS_NO_TITLE,
            link_kind,
            list_title or page_tit or title,
        )

    # 楼主区明示附件无权（PHPWind「用户组无法下载」）。
    # 勿扫全页：2048 打赏脚本含「请先登录再打赏」会误伤无附件磁链帖；
    # 仍有种子/txt 附件时先下，不要在此提前 stub。
    from parsers.attachments import thread_body_shows_attach_denied

    if (
        not has_lz_target
        and thread_body_shows_attach_denied(html)
        and (attachments_already_tried or not looks_like_attachment_zone(html))
    ):
        return ThreadOutcome("stub", "无权限下载附件", link_kind, title)

    # 龄期板（网友原创区等）：未满龄一律跳过，不占位、不抓附件
    if min_age > 0:
        posted_at = extract_thread_posted_at(html)
        if posted_at is not None and not is_thread_old_enough(
            posted_at, min_age_days=min_age
        ):
            return ThreadOutcome(
                "skipped",
                age_skip_tip(min_age),
                link_kind,
                title,
            )

    # 115sha 直链：只认楼主语料；已有 magnet/ed2k/目标链不跑重正则；有附件区则先下附件
    if not has_lz_target and has_115_sha_link(link_corpus):
        if should_skip_as_115sha_only(link_corpus):
            has_attach_corpus = "postmessage_attach" in (html or "")
            if not attachments_already_tried and looks_like_attachment_zone(html):
                pass  # 先下附件
            elif attachments_already_tried and not has_attach_corpus:
                # 附件已试但未注入（解压失败/空包）：勿把正文 115 目录误标成「附件跳过」
                pass
            else:
                return ThreadOutcome("skipped", SKIP_115SHA, link_kind, title)
        # 已有目标链：继续走正文导入 / 附件逻辑

    # 115 网盘分享页：有分享链则走正文解析入库（见 parse_thread_dual），不再跳过。
    # 仍跳过：仅标题写 115 分享、正文无实际链接（见下方 title 分支已移除分享标题硬跳）。

    # 网盘跳过口径（勿用正文关键字扫）：
    # 1) 标题只点名一种网盘，且无 115/ed2k/磁力；
    # 2) 资源链只含一种网盘 URL，且无 ed2k/磁力/115。
    # 标题或链上 115 与百度等并存 → 不判网盘；有附件区可先试附件。
    title_blocks_cloud = title_has_target_or_115_hint(title) or title_has_target_or_115_hint(
        list_title
    )
    cloud_hit = None if title_blocks_cloud else match_skip_cloud_share_link(link_corpus)
    if cloud_hit is not None and not has_lz_target:
        # 纯网盘（标题/链均无 115·ed2k·磁力）直接跳过；不再「先下附件」
        # （115 与网盘并存已由 title_blocks_cloud / 链上 115 排除）
        return ThreadOutcome("skipped", cloud_hit.skip_tip(), link_kind, title)

    # 标题仅 115sha / 各类网盘、且正文无目标链：
    # 115sha 标题若带附件区，先下附件（常见：标题写 115sha1，rar 内实为 ed2k）
    # （标题含 115/ed2k/磁力时不因「百度」等字样硬跳）
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
            return ThreadOutcome("skipped", SKIP_115SHA, link_kind, title)
    _has_body_target = has_lz_target
    if not _has_body_target and not title_blocks_cloud:
        title_cloud = match_skip_cloud_share_title(title) or match_skip_cloud_share_title(
            list_title
        )
        if title_cloud is not None:
            # 标题独占一种网盘 → 直接跳过（有附件也不先下）
            return ThreadOutcome(
                "skipped", title_cloud.skip_tip(from_title=True), link_kind, title
            )

    # 需回复：满龄（或非龄期板）→ 占位显示；未满龄已在上一步跳过
    if is_reply_required_post(html):
        return ThreadOutcome("stub", "需回复贴", link_kind, title)
    # 付费购买：跳过（不占位）；0 元由调用方先解锁，仍无链时在下方 stub
    if is_purchase_required_post(html):
        return ThreadOutcome("skipped", SKIP_PURCHASE, link_kind, title)

    # Body has target link? 仅认楼主语料（与 parse_thread_dual 一致）
    # 回帖/侧栏误检到的链不走进「有链无主资源」误杀。
    # 正文有链：先按正文 import；入库验收「不合格*」时由 pipeline 切块后再下附件复判。
    # 正文无链但有附件区：标 need_attachments（仅挂起）；下载在切块+卡片之后。
    if has_lz_target:
        # 已因不合格下过附件：无权/空 → 占位，勿用正文残链当真入库
        # （tid=3395138：正文仅部分链，完整链在无权附件里）
        if (
            attachments_already_tried
            and looks_like_attachment_zone(html)
            and not _body_has_multi_structured_targets(link_corpus, link_kind=link_kind)
            and (
                attachment_denied
                or attachment_login_required
                or attachment_failed
                or not had_attachments
            )
        ):
            return ThreadOutcome("stub", "无权限下载附件", link_kind, title)
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
            # 帖标题只认列表；parsed.title 可能是「提示信息」勿盖过
            display_title = coalesce_thread_title(list_title, title, parsed.title) or title
            if display_title and not title_recognizable(parsed.title):
                parsed.title = display_title
            # 附件注入后再判成功：文案标「附件」，避免误成「正文含目标链接」
            # 仅「已尝试附件」不够：空附件回落正文时仍算正文成功
            from_attach = bool(
                had_attachments
                or "postmessage_attach" in (html or "")
            )
            if outcome_kind == "115share":
                tip = (
                    "成功：附件含115分享码"
                    if from_attach
                    else "成功：正文含115分享码"
                )
            else:
                tip = (
                    "成功：附件解析出目标链接"
                    if from_attach
                    else "成功：正文含目标链接"
                )
            return ThreadOutcome(
                "import",
                tip,
                outcome_kind,
                display_title,
                parsed=parsed,
            )
        # 楼主语料检出目标链形态但解析无主资源：
        # 实为网盘 → 跳过；有附件区 → 继续下附件；否则已见正文、链落不成 → 跳过（勿标 failed）
        if not attachments_already_tried and not looks_like_attachment_zone(html):
            if is_non_target_cloud_share(link_kind=link_kind, text=link_corpus):
                return ThreadOutcome(
                    "skipped", SKIP_NON_RESOURCE, link_kind, title
                )
            cloud_fail = match_skip_cloud_share_link(link_corpus)
            if cloud_fail is not None:
                return ThreadOutcome("skipped", cloud_fail.skip_tip(), link_kind, title)
            return ThreadOutcome("skipped", SKIP_NO_TARGET, link_kind, title)

    # 0 元购买仍无链（未登录/未解锁）：占位，留给账号爬；勿再走附件/无磁力跳过
    if not has_lz_target and is_free_purchase_post(html):
        return ThreadOutcome("stub", "0元购买贴", link_kind, title)

    # 正文已写出下载链形态但 hash/URI 残缺（如特徵全碼 31 位）→ 跳过，勿盲下附件
    if not has_lz_target:
        from parsers.magnet import has_abnormal_download_link

        if has_abnormal_download_link(link_corpus) or has_abnormal_download_link(
            post_text(html) or ""
        ):
            return ThreadOutcome("skipped", SKIP_NON_RESOURCE, link_kind, title)

    # No usable body link yet — attachment strategy (ed2k-aligned)
    if not attachments_already_tried and looks_like_attachment_zone(html):
        if link_kind in {"magnet", "both"}:
            from parsers.attachments import pick_magnet_attachment_kind

            attach_kind = pick_magnet_attachment_kind(
                base_url or "", html, title=title or ""
            )
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

    # 附件无权 / 下载落到登录提示页：占位「无权限下载附件」（账号可重爬）
    if attachment_denied or attachment_login_required:
        return ThreadOutcome("stub", "无权限下载附件", link_kind, title)
    # 空壳种子（HTTP 200 但 body=0）：附件本身坏了，跳过勿重试
    if attachment_empty_torrent:
        return ThreadOutcome("skipped", "种子大小为0", link_kind, title)
    if attachment_failed:
        return ThreadOutcome("retry", "附件下载失败，待重试", link_kind, title)
    # 有附件区、已试、却没下到任何内容：登录墙常漏检 → 无权占位，勿跳过
    if (
        attachments_already_tried
        and not had_attachments
        and looks_like_attachment_zone(html)
    ):
        return ThreadOutcome("stub", "无权限下载附件", link_kind, title)
    # 附件已下载但抽不出 ed2k/磁力 → 区分 115sha，勿一律「未解析到」
    if had_attachments or attachments_already_tried:
        if should_skip_as_115sha_only(link_corpus):
            return ThreadOutcome(
                "skipped",
                SKIP_115SHA,
                link_kind,
                title,
            )
        return ThreadOutcome(
            "skipped",
            SKIP_NO_TARGET,
            link_kind,
            title,
        )

    if is_non_target_cloud_share(link_kind=link_kind, text=link_corpus) and not title_implies_resource(
        title, link_kind
    ):
        return ThreadOutcome("skipped", SKIP_NON_RESOURCE, link_kind, title)

    wrong_typeid = bool(
        required_typeid
        and fid == DISCUZ_BOARD_FID
        and thread_typeid_mismatch(html, str(fid), required_typeid)
    )
    if is_genuine_non_resource(html=html, title=title, link_kind=link_kind, text=link_corpus):
        return ThreadOutcome("skipped", SKIP_NON_RESOURCE, link_kind, title)

    if wrong_typeid:
        return ThreadOutcome("retry", "非情色分享分类，待复核", link_kind, title)
    # 正文/附件均无 ed2k、magnet → 跳过（含标题暗示资源）
    if title_implies_resource(title, link_kind):
        return ThreadOutcome("skipped", SKIP_NO_TARGET, link_kind, title)
    if len(html or "") < 8000:
        return ThreadOutcome("retry", "页面过短/未正常加载", link_kind, title)

    return ThreadOutcome("skipped", SKIP_NO_TARGET, link_kind, title)
