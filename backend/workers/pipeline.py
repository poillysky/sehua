"""Fetch HTML → judge outcome (ed2k-aligned) → persist upsert / stub."""

from __future__ import annotations

import logging
from typing import Any, Optional

from crawler.fetcher import Fetcher
from crawler.list_urls import list_url_for_board, site_root
from crawler.session import BASE_URL, SessionManager
from parsers.boards import get_board_policy
from parsers.links import DualParseResult, parse_thread_dual
from parsers.thread_gates import has_115_sha_link
from workers.session_factory import fetcher_from_config, session_from_config
from workers.thread_outcome import ThreadOutcome, judge_thread_html

log = logging.getLogger(__name__)


async def fetch_and_parse_thread(
    tid: int,
    *,
    board_fid: int | str,
    session: Optional[SessionManager] = None,
    preferred_link: Optional[str] = None,
    list_title: str = "",
    crawler_config: Optional[dict[str, Any]] = None,
) -> DualParseResult:
    """Session + dual parsers. Does not write DB — call persist_parsed / process_thread."""
    policy = get_board_policy(board_fid)
    preferred = preferred_link or policy.primary_link
    cfg = crawler_config or {}

    own_session = session is None
    session = session or (session_from_config(cfg) if cfg else SessionManager())
    fetcher = fetcher_from_config(session, cfg) if cfg else Fetcher(session)
    retries = int(cfg.get("web_crawler_fetch_retries") or 3)

    try:
        if not session._ready:
            await session.bootstrap()
        root = site_root(str(cfg.get("web_crawl_urls") or "").split(",")[0] if cfg else BASE_URL)
        list_url = list_url_for_board(board_fid, 1, root=root, policy=policy)
        thread_url = f"{root}thread-{tid}-1-1.html"
        fetcher.set_referer(list_url)
        html = await fetcher.get_thread_html(thread_url, retries=retries)

        result = parse_thread_dual(
            html, tid=tid, preferred_link=preferred, board_fid=board_fid
        )  # type: ignore[arg-type]
        if list_title and not (result.title or "").strip():
            result.title = list_title
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
) -> dict[str, Any]:
    """Full single-thread path: HTTP fetch → soft-browser retry → outcome → optional persist.

    preferred_link: 覆盖板块主链（如随机抓帖用 \"both\"）。
    html: 若已取到帖页 HTML 则复用，避免重复请求。
    """
    policy = get_board_policy(board_fid)
    persist_board_name = (board_name or policy.name or "").strip()
    link_pref = (preferred_link or policy.primary_link or "magnet").strip().lower()
    if link_pref not in {"magnet", "ed2k", "both"}:
        link_pref = policy.primary_link
    cfg = crawler_config or {}
    own_session = session is None
    session = session or (session_from_config(cfg) if cfg else SessionManager())
    own_fetcher = fetcher is None
    fetcher = fetcher or (fetcher_from_config(session, cfg) if cfg else Fetcher(session))
    retries = int(cfg.get("web_crawler_fetch_retries") or 3)

    root = site_root(str(cfg.get("web_crawl_urls") or "").split(",")[0] if cfg else BASE_URL)
    thread_url = f"{root}thread-{tid}-1-1.html"

    try:
        if not session._ready:
            await session.bootstrap()
        list_url = list_url_for_board(board_fid, 1, root=root, policy=policy)
        # 批量重爬共用 Fetcher 时也要随板块更新 Referer
        fetcher.set_referer(list_url)
        soft_browser_retried = False
        if html is None:
            # HTTP 读帖；软文/安全壳时 get_thread_html 内会浏览器整页重试
            html = await fetcher.get_thread_html(thread_url, retries=retries)
            soft_browser_retried = fetcher.last_soft_browser_retried

        # 按帖页回写二级板块（已入库重爬常带旧纯 fid / 空名）
        from parsers.thread_gates import resolve_thread_board_meta

        board_fid, persist_board_name = resolve_thread_board_meta(
            html,
            fallback_key=board_fid,
            fallback_name=persist_board_name,
        )
        policy = get_board_policy(board_fid)

        outcome = judge_thread_html(
            html,
            board_fid=board_fid,
            list_title=list_title,
            base_url=thread_url,
            soft_browser_retried=soft_browser_retried,
            preferred_link=link_pref,
        )
        # 兜底：判定仍要求浏览器重试且尚未做过
        if outcome.need_browser_retry and not soft_browser_retried:
            log.info("tid=%s soft-ad → force browser page read", tid)
            html = await fetcher.get_html(thread_url, mode="browser", retries=min(2, retries))
            soft_browser_retried = True
            board_fid, persist_board_name = resolve_thread_board_meta(
                html,
                fallback_key=board_fid,
                fallback_name=persist_board_name,
            )
            policy = get_board_policy(board_fid)
            outcome = judge_thread_html(
                html,
                board_fid=board_fid,
                list_title=list_title,
                base_url=thread_url,
                soft_browser_retried=True,
                preferred_link=link_pref,
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
            )
            attach_tried = True
            attachment_text = attach_res.text or ""
            if attachment_text and has_115_sha_link(attachment_text):
                log.info("tid=%s attachment has 115sha — skip", tid)
                outcome = ThreadOutcome(
                    "skipped",
                    "115sha 链接（附件，跳过）",
                    outcome.link_kind,
                    outcome.title or list_title,
                )
            else:
                if attachment_text:
                    html = inject_attachment_text(html, attachment_text)
                outcome = judge_thread_html(
                    html,
                    board_fid=board_fid,
                    list_title=list_title,
                    base_url=thread_url,
                    soft_browser_retried=soft_browser_retried,
                    attachments_already_tried=True,
                    attachment_denied=attach_res.denied,
                    attachment_failed=attach_res.failed and not attach_res.downloaded,
                    had_attachments=attach_res.downloaded or bool(attachment_text),
                    preferred_link=link_pref,
                )
                # 附件语料可能已含链但 judge 走了非 import：再双解析一次补全
                # skipped（含 115sha）不再抬升为 import
                if outcome.verdict not in {"import", "skipped"} and attachment_text:
                    merged = parse_thread_dual(
                        html,
                        tid=tid,
                        preferred_link=link_pref,  # type: ignore[arg-type]
                        extra_text=attachment_text,
                        base_url=thread_url,
                        board_fid=board_fid,
                    )
                    if merged.primary_link_kind != "none" and merged.assets:
                        outcome = ThreadOutcome(
                            "import",
                            "成功：附件解析出目标链接",
                            outcome.link_kind,
                            merged.title or outcome.title,
                            parsed=merged,
                        )

        parsed = outcome.parsed or parse_thread_dual(
            html,
            tid=tid,
            preferred_link=link_pref,  # type: ignore[arg-type]
            extra_text=attachment_text,
            base_url=thread_url,
            board_fid=board_fid,
        )
        if not parsed.title and (outcome.title or list_title):
            parsed.title = outcome.title or list_title
        # 确保描述按本板结构卡片重算（含 outcome.parsed 来自 judge 的路径）
        from parsers.content import build_structured_description

        parsed.description = build_structured_description(
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
            "attachment_chars": len(attachment_text),
            "soft_browser_retried": soft_browser_retried or outcome.soft_browser_retried,
            "title": parsed.title or outcome.title,
            "magnets": len(parsed.magnets),
            "ed2k": len(parsed.ed2k_links),
            "primary": parsed.primary_link_kind,
            "board_fid": str(board_fid),
            "board_name": persist_board_name,
            "persisted": None,
        }

        if persist and outcome.verdict in {"import", "stub"}:
            from db.connection import connect
            from db.persist import persist_dual_parse

            # For stub-only outcomes without assets, force stub path
            if outcome.verdict == "stub" and parsed.primary_link_kind != "none":
                # clear assets so persist writes stub (login/reply/purchase cases)
                parsed.assets = []
                parsed.magnets = []
                parsed.ed2k_links = []
                parsed.primary_link_kind = "none"

            conn = connect()
            try:
                result["persisted"] = persist_dual_parse(
                    conn,
                    parsed,
                    source_url=thread_url,
                    board_fid=board_fid,
                    board_name=persist_board_name,
                    forum_id="sehuatang",
                    import_outcome=str(outcome.outcome or outcome.label or ""),
                )
            finally:
                conn.close()
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
    from db.connection import connect
    from db.persist import persist_dual_parse

    conn = connect()
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
