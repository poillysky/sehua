"""管理端「解析测试」：浏览器过 18+ → HTTP 读帖 → 判定 / 附件（不入库）。"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from crawler.list_urls import list_url_for_board, site_root
from crawler.session import BASE_URL
from db.queue import canonical_thread_url, is_mobile_thread_url, tid_from_url
from parsers.attachments import extract_download_attachments
from parsers.boards import get_board_policy
from parsers.links import parse_thread_dual
from parsers.magnet import parse_magnet_text
from parsers.ed2k import parse_ed2k_text
from parsers.thread_gates import (
    has_115_sha_link,
    is_mobile_thread_shell,
    is_reply_required_post,
    is_safe_or_soft_shell,
    is_thread_access_denied,
    is_thread_login_required,
    looks_like_attachment_zone,
    page_title,
    post_text,
)
from workers.session_factory import (
    entry_urls_from_config,
    fetcher_from_config,
    session_from_config,
)
from workers.thread_outcome import VERDICT_LABELS, ThreadOutcome, judge_thread_html

log = logging.getLogger(__name__)

_FID_RE = re.compile(r"[?&]fid=(\d+)", re.I)
_FORUM_RE = re.compile(r"forum-(\d+)-", re.I)


def _infer_fid(url: str, html: str, fallback: str = "") -> str:
    if fallback and str(fallback).strip().isdigit():
        return str(fallback).strip()
    for pattern in (_FID_RE, _FORUM_RE):
        m = pattern.search(url or "")
        if m:
            return m.group(1)
    m = re.search(r'fid[=:]["\']?(\d+)', html or "", re.I)
    if m:
        return m.group(1)
    return ""


def _field_from_metadata(meta: dict[str, str], *keys: str) -> str:
    for key in keys:
        val = (meta.get(key) or "").strip()
        if val:
            return val
    return ""


def _import_verdict_fields(verdict: str, outcome: str, link_count: int) -> dict[str, Any]:
    label = VERDICT_LABELS.get(verdict, verdict)
    # 对齐 ed2k 前端字段名
    mapped = verdict
    if verdict == "need_attachments":
        mapped = "failed"
    elif verdict == "retry":
        mapped = "interstitial" if "软文" in outcome or "壳" in outcome else "failed"
    elif verdict == "skipped":
        mapped = "failed"
    return {
        "import_verdict": mapped if mapped in {"import", "stub", "interstitial", "failed"} else "failed",
        "import_verdict_label": label,
        "import_outcome": outcome,
        "import_link_count": link_count,
    }


async def parse_thread_for_admin(
    url: str,
    *,
    board_fid: str = "",
    proxy_override: str = "",
    crawler_config: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """使用本站混合抓取：浏览器过 18+ / 软文壳，HTTP 拉正文。默认不入库。"""
    original_url = (url or "").strip()
    if not original_url:
        raise ValueError("帖子 URL 不能为空")

    cfg = dict(crawler_config or {})
    proxy = (proxy_override or "").strip() or str(cfg.get("web_crawler_proxy") or "").strip()
    entries = entry_urls_from_config(cfg)
    root = site_root(entries[0] if entries else BASE_URL)
    input_was_mobile = is_mobile_thread_url(original_url)
    desktop_url = canonical_thread_url(original_url, root=root)
    tid = tid_from_url(desktop_url) or tid_from_url(original_url) or 0
    if not tid:
        raise ValueError("无法从 URL 解析 tid（请粘贴含 tid= 或 thread-数字 的桌面/手机链接）")

    session = session_from_config(cfg, proxy=proxy)
    fetcher = fetcher_from_config(session, cfg, proxy=proxy)
    retries = int(cfg.get("web_crawler_fetch_retries") or 3)

    try:
        await session.bootstrap(entry_urls=entries or None)
        # 用户显式选了板块 → 按该板块主链判定；留空 → 双链自动识别（仍可展示推断出的板块）
        fid_forced = bool((board_fid or "").strip())
        fid_hint = _infer_fid(original_url, "", board_fid if fid_forced else "")
        if not fid_hint and not fid_forced:
            fid_hint = str(cfg.get("active_board_fid") or "")
        board_fid_int = int(fid_hint) if str(fid_hint).isdigit() else 103
        policy = get_board_policy(board_fid_int)
        preferred_link = policy.primary_link if fid_forced else "both"
        list_url = list_url_for_board(board_fid_int, 1, root=root, policy=policy)
        # 始终打桌面帖；手机链接在规范化阶段已去掉 mobile / m.
        thread_url = canonical_thread_url(desktop_url or original_url, root=root)
        if not tid_from_url(thread_url):
            thread_url = f"{root}thread-{tid}-1-1.html"
        fetcher.set_referer(list_url)

        # HTTP 读帖；遇到 18+/软文壳时 Fetcher 内会浏览器整页重读
        html = await fetcher.get_thread_html(thread_url, retries=retries)
        soft_browser_retried = fetcher.last_soft_browser_retried
        mobile_shell = is_mobile_thread_shell(html)
        # 若仍像手机空壳，强制再抓一次桌面 URL
        if mobile_shell:
            log.info("parse-test tid=%s mobile shell → refetch desktop", tid)
            html = await fetcher.get_thread_html(thread_url, retries=retries)
            soft_browser_retried = soft_browser_retried or fetcher.last_soft_browser_retried
            mobile_shell = is_mobile_thread_shell(html)
            if mobile_shell:
                html = await fetcher.get_html(thread_url, mode="browser", retries=min(2, retries))
                soft_browser_retried = True
                mobile_shell = is_mobile_thread_shell(html)

        board_fid_str = _infer_fid(
            thread_url, html, board_fid if fid_forced else ""
        ) or str(board_fid_int)
        board_fid_int = int(board_fid_str) if board_fid_str.isdigit() else board_fid_int
        policy = get_board_policy(board_fid_int)
        if fid_forced:
            preferred_link = policy.primary_link

        outcome = judge_thread_html(
            html,
            board_fid=board_fid_int,
            soft_browser_retried=soft_browser_retried,
            preferred_link=preferred_link,
        )
        if outcome.need_browser_retry and not soft_browser_retried:
            log.info("parse-test tid=%s soft-ad → browser page", tid)
            html = await fetcher.get_html(thread_url, mode="browser", retries=min(2, retries))
            soft_browser_retried = True
            outcome = judge_thread_html(
                html,
                board_fid=board_fid_int,
                soft_browser_retried=True,
                preferred_link=preferred_link,
            )

        attachment_kind = outcome.attachment_kind
        attachment_text = ""
        attachment_denied = False
        attachment_failed = False
        attachment_downloaded = False
        attachment_source = ""
        if outcome.verdict == "need_attachments":
            from crawler.attachments import fetch_attachments_for_outcome
            from parsers.attachments import inject_attachment_text

            attach_timeout = float(cfg.get("web_crawler_timeout") or 45)
            attach_res = await fetch_attachments_for_outcome(
                session,
                html=html,
                thread_url=thread_url,
                attachment_kind=attachment_kind,
                timeout=max(15.0, attach_timeout),
            )
            attachment_denied = attach_res.denied
            attachment_failed = attach_res.failed and not attach_res.downloaded
            attachment_downloaded = attach_res.downloaded
            attachment_text = attach_res.text or ""
            attachment_source = attachment_kind or ""
            if attachment_text and has_115_sha_link(attachment_text):
                outcome = ThreadOutcome(
                    "skipped",
                    "115sha 链接（附件，跳过）",
                    outcome.link_kind,
                    outcome.title,
                )
            else:
                if attachment_text:
                    html = inject_attachment_text(html, attachment_text)
                outcome = judge_thread_html(
                    html,
                    board_fid=board_fid_int,
                    soft_browser_retried=soft_browser_retried,
                    attachments_already_tried=True,
                    attachment_denied=attachment_denied,
                    attachment_failed=attachment_failed,
                    had_attachments=attachment_downloaded or bool(attachment_text),
                    preferred_link=preferred_link,
                )
                # 双链模式下：种子失败再试电驴尾部附件
                if (
                    outcome.verdict not in {"import", "skipped"}
                    and preferred_link == "both"
                    and attachment_kind == "torrent"
                    and looks_like_attachment_zone(html)
                ):
                    attach_res2 = await fetch_attachments_for_outcome(
                        session,
                        html=html,
                        thread_url=thread_url,
                        attachment_kind="txt_tail",
                        timeout=max(15.0, attach_timeout),
                    )
                    attachment_denied = attachment_denied or attach_res2.denied
                    attachment_failed = attachment_failed or (attach_res2.failed and not attach_res2.downloaded)
                    attachment_downloaded = attachment_downloaded or attach_res2.downloaded
                    if attach_res2.text and has_115_sha_link(attach_res2.text):
                        attachment_text = (attachment_text + "\n" + attach_res2.text).strip()
                        attachment_source = "torrent+txt_tail" if attachment_source else "txt_tail"
                        outcome = ThreadOutcome(
                            "skipped",
                            "115sha 链接（附件，跳过）",
                            outcome.link_kind,
                            outcome.title,
                        )
                    elif attach_res2.text:
                        attachment_text = (attachment_text + "\n" + attach_res2.text).strip()
                        attachment_source = "torrent+txt_tail" if attachment_source else "txt_tail"
                        html = inject_attachment_text(html, attachment_text)
                        outcome = judge_thread_html(
                            html,
                            board_fid=board_fid_int,
                            soft_browser_retried=soft_browser_retried,
                            attachments_already_tried=True,
                            attachment_denied=attachment_denied,
                            attachment_failed=attachment_failed,
                            had_attachments=True,
                            preferred_link=preferred_link,
                        )
                if outcome.verdict not in {"import", "skipped"} and attachment_text:
                    merged = parse_thread_dual(
                        html,
                        tid=tid,
                        preferred_link=preferred_link,  # type: ignore[arg-type]
                        extra_text=attachment_text,
                        base_url=thread_url,
                        board_fid=board_fid_int,
                    )
                    if merged.primary_link_kind != "none" and merged.assets:
                        outcome = ThreadOutcome(
                            "import",
                            "成功：附件解析出目标链接",
                            merged.primary_link_kind,
                            merged.title or outcome.title,
                            parsed=merged,
                        )

        parsed = outcome.parsed or parse_thread_dual(
            html,
            tid=tid,
            preferred_link=preferred_link,  # type: ignore[arg-type]
            extra_text=attachment_text,
            base_url=thread_url,
            board_fid=board_fid_int,
        )
        if not parsed.title and outcome.title:
            parsed.title = outcome.title
        from parsers.content import build_structured_description

        parsed.description = build_structured_description(
            parsed.metadata,
            extract_password=parsed.extract_password,
            title=parsed.title,
            board_fid=board_fid_int,
        )

        body = post_text(html) or ""
        body_magnets = parse_magnet_text(body)
        body_ed2k = parse_ed2k_text(body)
        attachments = extract_download_attachments(thread_url, html)
        interstitial = is_safe_or_soft_shell(html)
        mobile_shell = is_mobile_thread_shell(html)
        login_required = is_thread_login_required(html)
        access_denied = is_thread_access_denied(html)
        reply_required = is_reply_required_post(html)
        meta = parsed.metadata or {}
        link_count = len(parsed.magnets) + len(parsed.ed2k_links)

        return {
            "input_url": original_url,
            "fetch_url": thread_url,
            "desktop_url": desktop_url or thread_url,
            "url_converted": bool(input_was_mobile) or (thread_url.rstrip("/") != original_url.rstrip("/")),
            "mobile_input": input_was_mobile,
            "mobile_shell": mobile_shell,
            "interstitial": interstitial,
            "title": parsed.title or page_title(html) or "",
            "page_title": page_title(html) or "",
            "resource_name": _field_from_metadata(
                meta, "资源名称", "影片名称", "片名", "名称"
            ),
            "description": parsed.description or "",
            "actress": _field_from_metadata(meta, "出演女优", "女优", "演员"),
            "coded": _field_from_metadata(meta, "是否有码", "有无码", "有码无码", "影片码别"),
            "watermark": _field_from_metadata(meta, "有无水印", "有无第三方水印", "水印"),
            "file_size": _field_from_metadata(
                meta, "文件大小", "影片容量", "影片大小", "资源大小", "大小"
            ),
            "resource_count": _field_from_metadata(meta, "资源数量", "数量"),
            "extract_password": parsed.extract_password or "",
            "board_fid": str(board_fid_int),
            "board_name": policy.name if policy else "",
            "link_kind": outcome.link_kind or parsed.primary_link_kind,
            "login_required": login_required,
            "access_denied": access_denied,
            "reply_required": reply_required,
            "attachment_source": attachment_source,
            "attachment_denied": attachment_denied,
            "attachment_failed": attachment_failed,
            "attachment_downloaded": attachment_downloaded,
            "attachment_text_len": len(attachment_text),
            "attachment_text_preview": (attachment_text or "")[:2000],
            "body_magnet_count": len(body_magnets),
            "body_ed2k_count": len(body_ed2k),
            "final_magnet_count": len(parsed.magnets),
            "final_ed2k_count": len(parsed.ed2k_links),
            "magnets": [
                {
                    "infohash": m.infohash,
                    "filename": m.filename,
                    "size": m.size,
                    "link": m.link,
                }
                for m in parsed.magnets
            ],
            "ed2k_links": [
                {"hash": e.hash, "filename": e.filename, "size": e.size, "link": e.link}
                for e in parsed.ed2k_links
            ],
            "attachments": [{"name": a.name, "kind": a.kind, "url": a.url} for a in attachments],
            "preview_images": list(parsed.preview_images or [])[:5],
            "html_len": len(html),
            "soft_browser_retried": soft_browser_retried,
            "fetch_mode": "browser→http" if soft_browser_retried else "http",
            "host": urlparse(thread_url).netloc,
            **_import_verdict_fields(outcome.verdict, outcome.outcome, link_count),
        }
    finally:
        await session.close()
