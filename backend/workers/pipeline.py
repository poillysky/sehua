"""Fetch HTML → judge outcome (ed2k-aligned) → persist upsert / stub."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from crawler.fetcher import Fetcher
from crawler.list_urls import site_root
from crawler.session import BASE_URL, SessionManager
from parsers.links import DualParseResult
from parsers.thread_gates import looks_like_attachment_zone, should_skip_as_115sha_only
from workers.cpu_jobs import (
    job_judge_thread_html,
    job_judge_with_attachment,
    job_parse_thread_dual,
)
from workers.cpu_pool import run_parse_job
from workers.session_factory import (
    bootstrap_probe_for_forum,
    resolve_forum_entry_urls,
    fetcher_from_config,
    session_from_config,
)
from workers.thread_outcome import ThreadOutcome

log = logging.getLogger(__name__)


async def _judge_html(
    html: str,
    *,
    board_fid: str | int,
    list_title: str,
    base_url: str,
    preferred_link: str,
    forum_id: str,
    tid: int,
    soft_browser_retried: bool = False,
    attachments_already_tried: bool = False,
    attachment_denied: bool = False,
    attachment_login_required: bool = False,
    attachment_failed: bool = False,
    had_attachments: bool = False,
    attachment_text: str = "",
) -> ThreadOutcome:
    """大附件/大页走进程池，避免 GIL 卡死管理端。"""
    payload: dict[str, Any] = {
        "html": html,
        "board_fid": board_fid,
        "list_title": list_title,
        "base_url": base_url,
        "soft_browser_retried": soft_browser_retried,
        "attachments_already_tried": attachments_already_tried,
        "attachment_denied": attachment_denied,
        "attachment_login_required": attachment_login_required,
        "attachment_failed": attachment_failed,
        "had_attachments": had_attachments,
        "preferred_link": preferred_link,
        "forum_id": forum_id,
        "tid": tid,
    }
    if attachment_text:
        payload["attachment_text"] = attachment_text
        return await run_parse_job(
            job_judge_with_attachment,
            payload,
            html=html,
            extra=attachment_text,
        )
    return await run_parse_job(
        job_judge_thread_html,
        payload,
        html=html,
        extra="",
    )


async def _parse_dual(
    html: str,
    *,
    tid: int,
    preferred_link: str,
    extra_text: str,
    base_url: str,
    board_fid: str | int,
) -> DualParseResult:
    payload = {
        "html": html,
        "tid": tid,
        "preferred_link": preferred_link,
        "extra_text": extra_text or "",
        "base_url": base_url,
        "board_fid": str(board_fid or ""),
    }
    return await run_parse_job(
        job_parse_thread_dual,
        payload,
        html=html,
        extra=extra_text or "",
    )


async def _outcome_from_heavy_attachment(
    html: str,
    *,
    tid: int,
    list_title: str,
    prior: ThreadOutcome,
    preferred_link: str,
    base_url: str,
    board_fid: str | int,
    attachment_text: str,
) -> ThreadOutcome:
    """大包附件：直接 parse(extra_text)，跳过整页注入再判（省一次进程池 judge）。"""
    from parsers.thread_gates import coalesce_thread_title, should_skip_as_115sha_only

    link_kind = prior.link_kind
    title = prior.title or list_title
    # 大包全是 115sha 时勿落成「未解析到」（与 pipeline 前置检查 / 轻附件路径对齐）
    if attachment_text and should_skip_as_115sha_only(attachment_text):
        return ThreadOutcome(
            "skipped",
            "115sha 链接（附件，跳过）",
            link_kind,
            title,
        )

    merged = await _parse_dual(
        html,
        tid=tid,
        preferred_link=preferred_link,
        extra_text=attachment_text,
        base_url=base_url,
        board_fid=board_fid,
    )
    if merged.primary_link_kind != "none" and merged.assets:
        display = coalesce_thread_title(list_title, prior.title, merged.title) or (
            prior.title or list_title or merged.title or ""
        )
        if display and not coalesce_thread_title(merged.title):
            merged.title = display
        tip = (
            "成功：附件含115分享码"
            if merged.primary_link_kind == "115share"
            else "成功：附件解析出目标链接"
        )
        return ThreadOutcome(
            "import",
            tip,
            merged.primary_link_kind,
            display,
            parsed=merged,
        )
    return ThreadOutcome(
        "skipped",
        "未解析到 ed2k/磁力（跳过）",
        link_kind,
        title,
        parsed=merged,
    )


async def fetch_and_parse_thread(
    tid: int,
    *,
    board_fid: int | str,
    session: Optional[SessionManager] = None,
    preferred_link: Optional[str] = None,
    list_title: str = "",
    crawler_config: Optional[dict[str, Any]] = None,
    forum_id: str = "sehuatang",
) -> DualParseResult:
    """Session + dual parsers. Does not write DB — call persist_parsed / process_thread."""
    from crawler.sites import get_site_adapter
    from crawler.parser_phpwind import parse_thread_phpwind

    adapter = get_site_adapter(forum_id)
    policy = adapter.get_board_policy(board_fid)
    preferred = preferred_link or policy.primary_link
    cfg = crawler_config or {}

    own_session = session is None
    session = session or (
        session_from_config(cfg, forum_id=forum_id) if cfg else SessionManager()
    )
    fetcher = fetcher_from_config(session, cfg) if cfg else Fetcher(session)
    retries = int(cfg.get("web_crawler_fetch_retries") or 3)

    try:
        entries = resolve_forum_entry_urls(cfg, forum_id) if cfg else []
        if not session._ready:
            probe = bootstrap_probe_for_forum(cfg, forum_id)
            await session.bootstrap(entry_urls=entries or None, probe_url=probe)
        root = site_root(
            session.active_entry_url or (entries[0] if entries else BASE_URL)
        )
        list_url = adapter.build_list_url(root, board_fid, 1)
        thread_url = adapter.build_thread_url(root, tid)
        fetcher.set_referer(list_url)
        html = await fetcher.get_thread_html(thread_url, retries=retries)

        result = await _parse_dual(
            html,
            tid=tid,
            preferred_link=preferred,
            extra_text="",
            base_url=thread_url,
            board_fid=board_fid,
        )
        if adapter.engine == "phpwind":
            detail = parse_thread_phpwind(html, tid=tid)
            if detail.title and not (result.title or "").strip():
                result.title = detail.title
        from parsers.thread_gates import coalesce_thread_title

        good_title = coalesce_thread_title(list_title, result.title)
        if good_title:
            result.title = good_title
        log.info(
            "parsed tid=%s magnets=%s ed2k=%s primary=%s",
            result.tid,
            len(result.magnets),
            len(result.ed2k_links),
            result.primary_link_kind,
        )
        return result
    finally:
        if own_session:
            await session.close()


_ACCOUNT_STUB_SKIP_OUTCOMES = frozenset({"需回复贴", "需购买贴", "0元购买贴"})


def _is_account_stub_skip_outcome(label: str) -> bool:
    s = str(label or "").strip()
    if not s:
        return False
    if s in _ACCOUNT_STUB_SKIP_OUTCOMES:
        return True
    return (
        s.startswith("需回复")
        or s.startswith("需购买")
        or s.startswith("0元购买")
    )


async def process_thread(
    tid: int,
    *,
    board_fid: int | str,
    board_name: str = "",
    session: Optional[SessionManager] = None,
    list_title: str = "",
    persist: bool = False,
    crawler_config: Optional[dict[str, Any]] = None,
    fetcher: Optional[Fetcher] = None,
    preferred_link: Optional[str] = None,
    html: Optional[str] = None,
    account_stub_pass: bool = False,
    forum_id: str = "sehuatang",
    replace_thread_assets: bool = False,
) -> dict[str, Any]:
    """Full single-thread path: HTTP fetch → soft-browser retry → outcome → optional persist.

    preferred_link: 覆盖板块主链（如随机抓帖用 \"both\"）。
    html: 若已取到帖页 HTML 则复用，避免重复请求。
    account_stub_pass: 账号爬占位时，需回复/需购买改为跳过且不写占位。
    replace_thread_assets: 重爬入库时删除同帖旧真链，只保留本次解析结果。
    """
    from crawler.sites import get_site_adapter
    from crawler.throttle import THROTTLE

    if THROTTLE.should_stop():
        return {
            "tid": tid,
            "verdict": "stopped",
            "outcome": "已请求停止",
            "skipped": True,
            "link_kind": "none",
        }

    adapter = get_site_adapter(forum_id)
    policy = adapter.get_board_policy(board_fid)
    persist_board_name = (board_name or policy.name or "").strip()
    link_pref = (preferred_link or policy.primary_link or "magnet").strip().lower()
    if link_pref not in {"magnet", "ed2k", "both"}:
        link_pref = policy.primary_link
    cfg = crawler_config or {}
    own_session = session is None
    session = session or (
        session_from_config(cfg, forum_id=forum_id) if cfg else SessionManager()
    )
    own_fetcher = fetcher is None
    fetcher = fetcher or (fetcher_from_config(session, cfg) if cfg else Fetcher(session))
    retries = int(cfg.get("web_crawler_fetch_retries") or 3)

    try:
        # 会话已就绪时勿每帖同步 expand 2048 发布页（可卡数秒）
        preferred = str(cfg.get("preferred_entry_url") or "").strip()
        entries: list[str] = []
        if not session._ready:
            entries = resolve_forum_entry_urls(cfg, forum_id) if cfg else []
            probe = bootstrap_probe_for_forum(cfg, forum_id)
            await session.bootstrap(entry_urls=entries or None, probe_url=probe)
        # 2048：{当日进站 BBS}/read.php?tid=N；域名跟 active/preferred，不写死
        if forum_id == "2048":
            root = site_root(
                session.active_entry_url
                or preferred
                or (entries[0] if entries else BASE_URL)
            )
        else:
            root = site_root(
                session.active_entry_url or (entries[0] if entries else BASE_URL)
            )
        thread_url = adapter.build_thread_url(root, tid)
        list_url = adapter.build_list_url(root, board_fid, 1)
        # 批量重爬共用 Fetcher 时也要随板块更新 Referer
        fetcher.set_referer(list_url)
        soft_browser_retried = False
        if html is None:
            # HTTP 读帖；软文/安全壳时 get_thread_html 内会浏览器整页重试
            html = await fetcher.get_thread_html(thread_url, retries=retries)
            soft_browser_retried = fetcher.last_soft_browser_retried

        # 0 元购买：先点购买链解锁正文；付费购买在 judge 里跳过
        from workers.purchase_unlock import unlock_free_purchase_html

        html, free_buy_note = await unlock_free_purchase_html(
            fetcher, html, thread_url, retries=retries
        )
        if free_buy_note:
            log.info("tid=%s free-purchase: %s", tid, free_buy_note)

        # 按帖页回写二级板块（已入库重爬常带旧纯 fid / 空名）；PHPWind 跳过 Discuz 元数据推断
        from crawler.sites import is_phpwind
        from parsers.thread_gates import resolve_thread_board_meta

        if not is_phpwind(forum_id):
            board_fid, persist_board_name = resolve_thread_board_meta(
                html,
                fallback_key=board_fid,
                fallback_name=persist_board_name,
            )
            policy = adapter.get_board_policy(board_fid)

        # 首判：普通帖页走线程池（勿因 ~80KB HTML 挤进唯一进程池 worker）。
        # 仅附件大语料 / 超大页 / 正文海量链 才进 cpu pool。
        outcome = await _judge_html(
            html,
            board_fid=board_fid,
            list_title=list_title,
            base_url=thread_url,
            soft_browser_retried=soft_browser_retried,
            preferred_link=link_pref,
            forum_id=forum_id,
            tid=tid,
        )
        # 0 元购买未解锁且仍无链：占位入库，留给账号爬补链
        if free_buy_note and outcome.verdict in {"skipped", "failed"}:
            tip = str(outcome.outcome or "")
            if (not tip) or ("未解析到" in tip) or ("非资源" in tip) or ("未发现" in tip):
                outcome = ThreadOutcome(
                    "stub",
                    "0元购买贴",
                    outcome.link_kind,
                    outcome.title or list_title,
                )
        elif free_buy_note and outcome.verdict == "stub" and not str(
            outcome.outcome or ""
        ).startswith("0元购买"):
            # 统一占位文案，便于账号爬识别
            if "需回复" not in str(outcome.outcome or ""):
                outcome = ThreadOutcome(
                    "stub",
                    "0元购买贴",
                    outcome.link_kind,
                    outcome.title or list_title,
                )
        # 兜底：软文壳 / 空提示页 → 浏览器整页重读
        if outcome.need_browser_retry and not soft_browser_retried:
            reason = "soft-ad" if "软文" in str(outcome.outcome or "") else "tip-page"
            log.info("tid=%s %s → force browser page read", tid, reason)
            html = await fetcher.get_html(thread_url, mode="browser", retries=min(2, retries))
            soft_browser_retried = True
            # 浏览器过壳后再试一次 0 元购买解锁
            html, free_buy_note2 = await unlock_free_purchase_html(
                fetcher, html, thread_url, retries=retries
            )
            if free_buy_note2:
                free_buy_note = free_buy_note2
                log.info("tid=%s free-purchase(after browser): %s", tid, free_buy_note2)
            if not is_phpwind(forum_id):
                board_fid, persist_board_name = resolve_thread_board_meta(
                    html,
                    fallback_key=board_fid,
                    fallback_name=persist_board_name,
                )
                policy = adapter.get_board_policy(board_fid)
            outcome = await _judge_html(
                html,
                board_fid=board_fid,
                list_title=list_title,
                base_url=thread_url,
                soft_browser_retried=True,
                preferred_link=link_pref,
                forum_id=forum_id,
                tid=tid,
            )
            if free_buy_note and outcome.verdict in {"skipped", "failed"}:
                tip = str(outcome.outcome or "")
                if (not tip) or ("未解析到" in tip) or ("非资源" in tip) or ("未发现" in tip):
                    outcome = ThreadOutcome(
                        "stub",
                        "0元购买贴",
                        outcome.link_kind,
                        outcome.title or list_title,
                    )
        attachment_kind = outcome.attachment_kind
        attachment_text = ""
        attach_tried = False
        if outcome.verdict == "need_attachments":
            from crawler.attachments import fetch_attachments_for_outcome
            from parsers.attachments import inject_attachment_text

            log.info(
                "tid=%s need_attachments kind=%s — download & parse",
                tid,
                attachment_kind,
            )
            attach_timeout = float(cfg.get("web_crawler_timeout") or 45)
            attach_res = await fetch_attachments_for_outcome(
                session,
                html=html,
                thread_url=thread_url,
                attachment_kind=attachment_kind,
                timeout=max(15.0, attach_timeout),
                preferred_link=link_pref,
            )
            attach_tried = True
            attachment_text = attach_res.text or ""
            if attachment_text and should_skip_as_115sha_only(attachment_text):
                log.info("tid=%s attachment has 115sha — skip", tid)
                outcome = ThreadOutcome(
                    "skipped",
                    "115sha 链接（附件，跳过）",
                    outcome.link_kind,
                    outcome.title or list_title,
                )
            else:
                # 轻附件主进程注入再判；大包（≥24KB）直接 parse，跳过整页注入+judge
                heavy_attach = len(attachment_text) >= 24_000
                login_req = bool(getattr(attach_res, "login_required", False))
                if (
                    heavy_attach
                    and attachment_text
                    and not attach_res.denied
                    and not login_req
                ):
                    log.info(
                        "tid=%s heavy attachment fast-path chars=%s (skip re-judge)",
                        tid,
                        len(attachment_text),
                    )
                    outcome = await _outcome_from_heavy_attachment(
                        html,
                        tid=tid,
                        list_title=list_title,
                        prior=outcome,
                        preferred_link=link_pref,
                        base_url=thread_url,
                        board_fid=board_fid,
                        attachment_text=attachment_text,
                    )
                else:
                    if attachment_text and not heavy_attach:
                        html = inject_attachment_text(html, attachment_text)
                    outcome = await _judge_html(
                        html,
                        board_fid=board_fid,
                        list_title=list_title,
                        base_url=thread_url,
                        soft_browser_retried=soft_browser_retried,
                        attachments_already_tried=True,
                        attachment_denied=attach_res.denied,
                        attachment_login_required=login_req,
                        attachment_failed=attach_res.failed and not attach_res.downloaded,
                        had_attachments=attach_res.downloaded or bool(attachment_text),
                        preferred_link=link_pref,
                        forum_id=forum_id,
                        tid=tid,
                        attachment_text=attachment_text if heavy_attach else "",
                    )
                # 电驴板：txt/zip/excel 无果再试种子；磁力/双链：种子无果再试 txt/excel
                # stub/无权/需登录不再二轮（已能判定）；仅 retry/failed 等才回退
                if (
                    outcome.verdict not in {"import", "skipped", "stub"}
                    and not attach_res.denied
                    and not getattr(attach_res, "login_required", False)
                    and looks_like_attachment_zone(html)
                    and (
                        (link_pref == "ed2k" and attachment_kind == "txt_tail")
                        or (
                            link_pref in {"magnet", "both"}
                            and attachment_kind == "torrent"
                        )
                    )
                ):
                    next_kind = "torrent" if attachment_kind == "txt_tail" else "txt_tail"
                    log.info("tid=%s fallback attachments kind=%s", tid, next_kind)
                    attach_res2 = await fetch_attachments_for_outcome(
                        session,
                        html=html,
                        thread_url=thread_url,
                        attachment_kind=next_kind,
                        timeout=max(15.0, attach_timeout),
                        preferred_link=link_pref,
                    )
                    if attach_res2.text and should_skip_as_115sha_only(attach_res2.text):
                        attachment_text = (attachment_text + "\n" + attach_res2.text).strip()
                        outcome = ThreadOutcome(
                            "skipped",
                            "115sha 链接（附件，跳过）",
                            outcome.link_kind,
                            outcome.title or list_title,
                        )
                    elif attach_res2.text:
                        attachment_text = (attachment_text + "\n" + attach_res2.text).strip()
                        heavy2 = len(attachment_text) >= 24_000
                        login2 = bool(
                            getattr(attach_res, "login_required", False)
                            or getattr(attach_res2, "login_required", False)
                        )
                        if (
                            heavy2
                            and attachment_text
                            and not (attach_res.denied or attach_res2.denied)
                            and not login2
                        ):
                            log.info(
                                "tid=%s heavy attachment fast-path (fallback) chars=%s",
                                tid,
                                len(attachment_text),
                            )
                            outcome = await _outcome_from_heavy_attachment(
                                html,
                                tid=tid,
                                list_title=list_title,
                                prior=outcome,
                                preferred_link=link_pref,
                                base_url=thread_url,
                                board_fid=board_fid,
                                attachment_text=attachment_text,
                            )
                        else:
                            if not heavy2:
                                html = inject_attachment_text(html, attachment_text)
                            outcome = await _judge_html(
                                html,
                                board_fid=board_fid,
                                list_title=list_title,
                                base_url=thread_url,
                                soft_browser_retried=soft_browser_retried,
                                attachments_already_tried=True,
                                attachment_denied=attach_res.denied or attach_res2.denied,
                                attachment_login_required=login2,
                                attachment_failed=(
                                    (attach_res.failed and not attach_res.downloaded)
                                    or (attach_res2.failed and not attach_res2.downloaded)
                                ),
                                had_attachments=True,
                                preferred_link=link_pref,
                                forum_id=forum_id,
                                tid=tid,
                                attachment_text=attachment_text if heavy2 else "",
                            )
                    attachment_kind = f"{attachment_kind}+{next_kind}"
                # 附件语料可能已含链但 judge 走了非 import：再双解析一次补全
                # skipped（含 115sha）不再抬升为 import
                if outcome.verdict not in {"import", "skipped"} and attachment_text:
                    merged = await _parse_dual(
                        html,
                        tid=tid,
                        preferred_link=link_pref,
                        extra_text=attachment_text,
                        base_url=thread_url,
                        board_fid=board_fid,
                    )
                    if merged.primary_link_kind != "none" and merged.assets:
                        from parsers.thread_gates import coalesce_thread_title

                        display = coalesce_thread_title(
                            list_title, outcome.title, merged.title
                        ) or (outcome.title or list_title or merged.title or "")
                        if display and not coalesce_thread_title(merged.title):
                            merged.title = display
                        outcome = ThreadOutcome(
                            "import",
                            "成功：附件解析出目标链接",
                            outcome.link_kind,
                            display,
                            parsed=merged,
                        )

        if outcome.parsed is not None:
            parsed = outcome.parsed
            log.info(
                "tid=%s reuse judge.parsed assets=%s (skip 2nd parse)",
                tid,
                len(parsed.assets),
            )
        else:
            parsed = await _parse_dual(
                html,
                tid=tid,
                preferred_link=link_pref,
                extra_text=attachment_text,
                base_url=thread_url,
                board_fid=board_fid,
            )
        if attach_tried and attachment_text:
            parsed.had_attachments = True
        # 仅「附件」文案不够：attachments_already_tried 时空附件也会写成「附件解析出…」
        if (
            outcome.verdict == "import"
            and "附件" in str(outcome.outcome or "")
            and bool(attachment_text)
        ):
            parsed.had_attachments = True
        if adapter.engine == "phpwind":
            from crawler.parser_phpwind import parse_thread_phpwind

            detail = parse_thread_phpwind(html, tid=tid)
            if detail.title and not (parsed.title or "").strip():
                parsed.title = detail.title
        # 无权/登录页 extract_title 常为「提示信息」，列表标题优先；伪标题一律清空
        from parsers.thread_gates import coalesce_thread_title, title_recognizable

        good_title = coalesce_thread_title(list_title, outcome.title, parsed.title)
        if good_title:
            parsed.title = good_title
        elif not title_recognizable(parsed.title):
            parsed.title = ""
        # 确保描述按本板结构卡片重算（含 outcome.parsed 来自 judge 的路径）
        from parsers.content import build_structured_description

        parsed.description = await asyncio.to_thread(
            build_structured_description,
            parsed.metadata,
            extract_password=parsed.extract_password,
            title=parsed.title,
            board_fid=board_fid,
        )
        # 附件无权占位：把附件名写入描述，便于账号重爬识别
        if outcome.verdict == "stub" and "附件" in str(outcome.outcome or ""):
            from parsers.attachments import extract_download_attachments

            att_names = [
                a.name for a in extract_download_attachments(thread_url, html)[:6]
            ]
            if att_names:
                extra = "附件：" + "、".join(att_names)
                if extra not in (parsed.description or ""):
                    parsed.description = (
                        f"{parsed.description}\n{extra}".strip()
                        if parsed.description
                        else extra
                    )

        # 账号爬占位：登录后仍是需回复/需购买 → 跳过，不落新占位
        if (
            account_stub_pass
            and outcome.verdict == "stub"
            and _is_account_stub_skip_outcome(str(outcome.outcome or ""))
        ):
            outcome = ThreadOutcome(
                "skipped",
                f"{outcome.outcome}（账号爬跳过）",
                outcome.link_kind,
                outcome.title or list_title,
            )

        attach_chars = len(attachment_text or "")
        # 解析已完成：尽快丢掉整页 HTML / 附件语料，写库前不必再占峰
        html = ""
        attachment_text = ""

        result: dict[str, Any] = {
            "tid": tid,
            "thread_url": thread_url,
            "verdict": outcome.verdict,
            "verdict_label": outcome.label,
            "outcome": outcome.outcome,
            "link_kind": outcome.link_kind,
            "need_attachments": outcome.need_attachments,
            "attachment_kind": attachment_kind,
            "attachments_tried": attach_tried,
            "attachment_chars": attach_chars,
            "soft_browser_retried": soft_browser_retried or outcome.soft_browser_retried,
            "title": coalesce_thread_title(list_title, outcome.title, parsed.title)
            or (parsed.title or outcome.title or list_title),
            "magnets": len(parsed.magnets),
            "ed2k": len(parsed.ed2k_links),
            "asset_count": len(parsed.assets),
            "primary": parsed.primary_link_kind,
            "board_fid": str(board_fid),
            "board_name": persist_board_name,
            "persisted": None,
        }

        if persist and outcome.verdict in {"import", "stub"}:
            from db.resource_db import connect_resource
            from db.persist import persist_dual_parse
            from parsers.thread_gates import title_recognizable as _title_ok

            # For stub-only outcomes without assets, force stub path
            if outcome.verdict == "stub" and parsed.primary_link_kind != "none":
                # clear assets so persist writes stub (login/reply/purchase cases)
                parsed.assets = []
                parsed.magnets = []
                parsed.ed2k_links = []
                parsed.primary_link_kind = "none"

            # 占位必须有可识别标题，禁止「提示信息」入库
            if outcome.verdict == "stub" and not _title_ok(parsed.title):
                result["persisted"] = {
                    "count": 0,
                    "stub": False,
                    "link_kind": "skipped_tip_title",
                    "import_outcome": "伪标题拒绝占位",
                }
            else:

                def _persist_sync() -> dict[str, Any]:
                    conn = connect_resource()
                    try:
                        return persist_dual_parse(
                            conn,
                            parsed,
                            source_url=thread_url,
                            board_fid=board_fid,
                            board_name=persist_board_name,
                            forum_id=forum_id,
                            import_outcome=str(outcome.outcome or outcome.label or ""),
                            replace_thread_assets=replace_thread_assets,
                        )
                    finally:
                        conn.close()

                # 同步写库放到线程，避免堵住 FastAPI 事件循环导致管理端假死
                result["persisted"] = await asyncio.to_thread(_persist_sync)
                # 对外 outcome 以入库验收为准，禁止「成功」假象盖住不合格
                persisted = result.get("persisted") or {}
                final_out = str(persisted.get("import_outcome") or "").strip()
                if final_out:
                    result["outcome"] = final_out
                pv = str(persisted.get("verdict") or "")
                if pv in {"structure_fail", "content_gap"}:
                    result["structure_verdict"] = pv
        elif persist and outcome.verdict == "failed":
            result["persisted"] = {"count": 0, "stub": False, "link_kind": "failed"}

        return result
    finally:
        if own_session:
            await session.close()


def persist_parsed(
    parsed: DualParseResult,
    *,
    board_fid: int | str,
    board_name: str = "",
    source_url: str,
) -> dict:
    """Write DualParseResult into ed2k_resources + resource_sources."""
    from db.resource_db import connect_resource
    from db.persist import persist_dual_parse

    conn = connect_resource()
    try:
        return persist_dual_parse(
            conn,
            parsed,
            source_url=source_url,
            board_fid=board_fid,
            board_name=board_name,
        )
    finally:
        conn.close()
