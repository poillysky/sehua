"""已入库资源单帖 / 批量重爬。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from crawler.fetcher import Fetcher
from crawler.session import SessionManager
from db.connection import connect
from db.forum_configs import SITE_CRAWLER_FORUM_ID, load_forum_configs_map
from db.queue import (
    mark_pending_retry,
    mark_pending_soft_ad,
    mark_thread_done,
    mark_thread_skipped,
    requeue_for_recrawl,
    tid_from_url,
)
from db.repository import delete_resource_by_hash, delete_stub_by_source_url, get_resource_by_hash
from parsers.thread_gates import title_recognizable
from db.settings_store import get_setting
from parsers.boards import BOARD_POLICIES
from workers.pipeline import process_thread
from workers.runner import (
    _log_activity,
    crawl_status,
    end_exclusive,
    try_begin_exclusive,
)
from workers.session_factory import fetcher_from_config, session_from_config

log = logging.getLogger(__name__)

_IMPORT_VERDICTS = frozenset({"import", "stub"})


def _load_crawler_cfg(conn: Any) -> dict[str, Any]:
    configs = load_forum_configs_map(conn)
    cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
    proxy = get_setting(conn, "web_crawler_proxy", "")
    if proxy and not cfg.get("web_crawler_proxy"):
        cfg["web_crawler_proxy"] = proxy
    return cfg


def _resolve_item(conn: Any, resource_hash: str, cfg: dict[str, Any]) -> dict[str, Any]:
    item = get_resource_by_hash(conn, resource_hash)
    if not item:
        return {"ok": False, "hash": resource_hash, "error": "未找到该资源"}
    source_url = (item.get("source_url") or "").strip()
    if not source_url:
        return {"ok": False, "hash": resource_hash, "error": "该资源没有帖子来源 URL，无法重爬"}
    tid = tid_from_url(source_url)
    if not tid:
        return {
            "ok": False,
            "hash": resource_hash,
            "error": f"无法从来源 URL 解析 tid：{source_url}",
        }

    board_fid_s = str(item.get("board_fid") or "").strip()
    if not board_fid_s:
        board_fid_s = str(cfg.get("active_board_fid") or "")
    if not board_fid_s.isdigit() or int(board_fid_s) not in BOARD_POLICIES:
        return {"ok": False, "hash": resource_hash, "error": "缺少有效板块 fid，无法重爬"}
    board_fid = int(board_fid_s)
    board_name = str(item.get("board_name") or BOARD_POLICIES[board_fid].name)
    title = str(item.get("title") or item.get("filename") or "")
    queued = requeue_for_recrawl(
        conn,
        url=source_url,
        board_fid=board_fid,
        board_name=board_name,
        title=title,
        forum_id=SITE_CRAWLER_FORUM_ID,
    )
    return {
        "ok": True,
        "hash": resource_hash,
        "tid": tid,
        "board_fid": board_fid,
        "board_name": board_name,
        "title": title,
        "url": str(queued["url"]),
        "link_kind": str(item.get("link_kind") or ""),
        "ed2k_link": str(item.get("ed2k_link") or ""),
    }


def _apply_queue_outcome(
    conn: Any,
    thread_url: str,
    outcome: dict[str, Any],
) -> None:
    verdict = str(outcome.get("verdict") or "failed")
    if verdict == "import":
        mark_thread_done(conn, thread_url, outcome=str(outcome.get("outcome") or "import"))
    elif verdict == "stub":
        mark_thread_done(conn, thread_url, outcome=str(outcome.get("outcome") or "stub"))
    elif verdict == "skipped":
        mark_thread_skipped(conn, thread_url, str(outcome.get("outcome") or "skipped"))
    elif verdict == "retry" or "软文" in str(outcome.get("outcome") or ""):
        if outcome.get("soft_browser_retried") or "软文" in str(outcome.get("outcome") or ""):
            mark_pending_soft_ad(conn, thread_url, backoff_seconds=3600)
        else:
            mark_pending_retry(
                conn,
                thread_url,
                str(outcome.get("outcome") or "retry"),
                backoff_seconds=900,
            )
    elif verdict == "need_attachments":
        mark_pending_retry(conn, thread_url, "need_attachments", backoff_seconds=600)
    else:
        mark_thread_done(
            conn,
            thread_url,
            outcome=str(outcome.get("outcome") or "failed"),
            status="failed",
        )


async def _run_one(
    prepared: dict[str, Any],
    *,
    cfg: dict[str, Any],
    session: Optional[SessionManager] = None,
    fetcher: Optional[Fetcher] = None,
) -> dict[str, Any]:
    tid = int(prepared["tid"])
    board_fid = int(prepared["board_fid"])
    board_name = str(prepared["board_name"])
    title = str(prepared["title"])
    thread_url = str(prepared["url"])
    resource_hash = str(prepared["hash"])

    _log_activity(f"已入库重爬 · tid={tid} · {title[:40]}")
    try:
        outcome = await process_thread(
            tid,
            board_fid=board_fid,
            board_name=board_name,
            list_title=title,
            persist=True,
            crawler_config=cfg,
            session=session,
            fetcher=fetcher,
        )
    except Exception as exc:
        log.exception("recrawl failed")
        conn = connect()
        try:
            mark_pending_retry(conn, thread_url, str(exc)[:200], backoff_seconds=600)
        finally:
            conn.close()
        _log_activity(f"已入库重爬失败 · tid={tid} · {exc}")
        return {
            "ok": False,
            "imported": False,
            "hash": resource_hash,
            "tid": tid,
            "url": thread_url,
            "error": str(exc),
        }

    verdict = str(outcome.get("verdict") or "failed")
    removed = False
    conn = connect()
    try:
        _apply_queue_outcome(conn, thread_url, outcome)
        # 跳过/无效帖：清掉原占位行（如「提示信息」），否则重爬后仍挂在列表里
        if verdict == "skipped":
            is_stub = (prepared.get("link_kind") or "") == "stub" or str(
                prepared.get("ed2k_link") or ""
            ).lower().startswith("unavailable://")
            junk_title = not title_recognizable(title)
            if is_stub or junk_title:
                removed = delete_resource_by_hash(conn, resource_hash) or delete_stub_by_source_url(
                    conn, thread_url
                )
                if removed:
                    _log_activity(f"已入库重爬 · 删除无效占位 tid={tid}")
    finally:
        conn.close()

    imported = verdict in _IMPORT_VERDICTS
    persisted = outcome.get("persisted") or {}
    label = outcome.get("verdict_label") or verdict
    if removed:
        label = f"{label} · 已删占位"
    _log_activity(f"已入库重爬结束 · tid={tid} · {label}")
    return {
        "ok": imported or removed,
        "imported": imported,
        "removed": removed,
        "hash": resource_hash,
        "tid": tid,
        "url": thread_url,
        "verdict": verdict,
        "verdict_label": label,
        "outcome": outcome.get("outcome"),
        "persisted": persisted,
        "note": "跳过时会删除无效占位；正常入库则同 hash 覆盖",
        "error": None if (imported or removed) else str(outcome.get("verdict_label") or verdict),
    }


async def recrawl_imported_resource(resource_hash: str) -> dict[str, Any]:
    """按资源 hash 重爬来源帖：重置队列 → 抓帖入库（同 hash 覆盖，不新增）。"""
    batch = await recrawl_imported_resources([resource_hash])
    items = list(batch.get("items") or [])
    if items:
        return items[0]
    return {
        "ok": False,
        "imported": False,
        "error": str(batch.get("error") or "重爬失败"),
        "reason": batch.get("reason"),
    }


async def recrawl_imported_resources(hashes: list[str]) -> dict[str, Any]:
    """批量已入库重爬。

    - 连续调度中：只重新入队，由调度吃队列（避免每条开浏览器且被 busy 挡掉）
    - 空闲：占用 running，共用一个会话顺序抓完
    """
    cleaned: list[str] = []
    seen: set[str] = set()
    for h in hashes:
        key = (h or "").strip()
        if len(key) < 8 or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    if not cleaned:
        return {"ok": False, "error": "未提供有效 hash", "items": [], "imported": 0, "queued": 0}

    st = crawl_status()
    looping = bool(st.get("looping"))

    conn = connect()
    try:
        cfg = _load_crawler_cfg(conn)
        prepared_list: list[dict[str, Any]] = []
        prep_errors: list[dict[str, Any]] = []
        for h in cleaned:
            prep = _resolve_item(conn, h, cfg)
            if prep.get("ok"):
                prepared_list.append(prep)
            else:
                prep_errors.append(
                    {
                        "ok": False,
                        "imported": False,
                        "hash": h,
                        "error": prep.get("error") or "准备失败",
                    }
                )
    finally:
        conn.close()

    if not prepared_list and prep_errors:
        return {
            "ok": False,
            "mode": "failed",
            "error": prep_errors[0].get("error") or "准备失败",
            "items": prep_errors,
            "imported": 0,
            "queued": 0,
            "failed": len(prep_errors),
        }

    # 连续调度开着：只入队，让循环抓——以前 busy 直接拒绝导致批量几乎无法多条入库
    if looping:
        items = [
            {
                "ok": True,
                "imported": False,
                "queued": True,
                "hash": p["hash"],
                "tid": p["tid"],
                "url": p["url"],
                "title": p["title"],
                "note": "已重新入队，等待连续调度抓取入库",
            }
            for p in prepared_list
        ] + prep_errors
        _log_activity(f"已入库批量重爬 · 入队 {len(prepared_list)} 条（连续调度中）")
        return {
            "ok": True,
            "mode": "queued",
            "items": items,
            "imported": 0,
            "queued": len(prepared_list),
            "failed": len(prep_errors),
            "note": "连续调度进行中：已全部重新入队，由调度依次抓取入库",
        }

    lock = try_begin_exclusive("recrawl")
    if not lock.get("ok"):
        return {
            "ok": False,
            "skipped": True,
            "reason": lock.get("reason") or "busy",
            "error": lock.get("error") or "爬虫正在执行，请稍后再重爬",
            "items": prep_errors,
            "imported": 0,
            "queued": 0,
            "failed": len(prep_errors),
        }

    session: Optional[SessionManager] = None
    fetcher: Optional[Fetcher] = None
    results: list[dict[str, Any]] = list(prep_errors)
    imported_n = 0
    removed_n = 0
    try:
        _log_activity(f"已入库批量重爬 · 开始 {len(prepared_list)} 条")
        session = session_from_config(cfg)
        await session.bootstrap()
        fetcher = fetcher_from_config(session, cfg)

        for i, prepared in enumerate(prepared_list):
            one = await _run_one(prepared, cfg=cfg, session=session, fetcher=fetcher)
            results.append(one)
            if one.get("imported"):
                imported_n += 1
            if one.get("removed"):
                removed_n += 1
            # 给站点一点间隔，降低第二条起被拦的概率
            if i + 1 < len(prepared_list):
                await asyncio.sleep(0.8)
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        end_exclusive()

    failed_n = sum(
        1
        for r in results
        if not r.get("imported") and not r.get("queued") and not r.get("removed")
    )
    _log_activity(
        f"已入库批量重爬结束 · 入库 {imported_n}"
        + (f" · 删占位 {removed_n}" if removed_n else "")
        + f" · 失败 {failed_n}"
    )
    return {
        "ok": imported_n > 0 or removed_n > 0 or failed_n == 0,
        "mode": "immediate",
        "items": results,
        "imported": imported_n,
        "removed": removed_n,
        "queued": 0,
        "failed": failed_n,
        "note": "跳过无效占位会删除；正常则同 hash 覆盖",
    }
