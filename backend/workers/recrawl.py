"""已入库资源单帖 / 批量重爬。"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from crawler.fetcher import Fetcher
from crawler.session import SessionManager
from db.connection import connect
from db.forum_configs import SITE_CRAWLER_FORUM_ID, load_forum_configs_map
from db.queue import (
    ACCOUNT_DISCARDED_KINDS,
    DISCARDED_REQUEUE_KINDS,
    count_discarded_kind,
    list_discarded_by_tids,
    list_discarded_kind,
    mark_pending_retry,
    mark_thread_done,
    mark_thread_skipped,
    requeue_discarded_by_tids,
    requeue_for_recrawl,
    tid_from_url,
)
from db.repository import (
    count_priority_account_stubs,
    delete_resource_by_hash,
    delete_stub_by_source_url,
    get_resource_by_hash,
    list_priority_account_stubs,
)
from db.resource_db import connect_resource
from parsers.thread_gates import title_recognizable
from db.settings_store import get_setting
from parsers.boards import get_board_fid, get_board_policy
from workers.pipeline import process_thread
from workers.runner import (
    THROTTLE,
    _STATE,
    _log_activity,
    crawl_status,
    end_exclusive,
    try_begin_exclusive,
)
from workers.session_factory import fetcher_from_config, session_from_config

log = logging.getLogger(__name__)

_IMPORT_VERDICTS = frozenset({"import", "stub"})
_ACCOUNT_STUB_SKIP_OUTCOMES = frozenset({"需回复贴", "需购买贴"})


def _is_reply_or_purchase_outcome(label: str) -> bool:
    s = str(label or "")
    return s in _ACCOUNT_STUB_SKIP_OUTCOMES or "需回复" in s or "需购买" in s


def _empty_account_stub_progress(*, active: bool = False, remaining: int = 0) -> dict[str, Any]:
    return {
        "active": active,
        "remaining": int(remaining),
        "budget": int(remaining),  # 兼容旧前端字段：队列剩余
        "done": 0,
        "upgraded": 0,
        "still_stub": 0,
        "failed": 0,
        "skipped_prep": 0,
        "current_tid": None,
        "current_title": "",
    }


def _count_account_discarded(conn: Any) -> int:
    total = 0
    for kind in ACCOUNT_DISCARDED_KINDS:
        total += int(count_discarded_kind(conn, kind) or 0)
    return total


def _db_priority_remaining(*, exclude_hashes: list[str] | None = None) -> int:
    conn = connect_resource()
    try:
        stubs = count_priority_account_stubs(conn, exclude_hashes=exclude_hashes)
    finally:
        conn.close()
    qconn = connect()
    try:
        discarded = _count_account_discarded(qconn)
    finally:
        qconn.close()
    return int(stubs) + int(discarded)


def _publish_account_stub_progress(
    *,
    active: bool,
    remaining: int | None = None,
    done: int = 0,
    upgraded: int = 0,
    still_stub: int = 0,
    failed: int = 0,
    skipped_prep: int = 0,
    current_tid: int | None = None,
    current_title: str = "",
    exclude_hashes: list[str] | None = None,
) -> None:
    if remaining is None:
        try:
            remaining = _db_priority_remaining(exclude_hashes=exclude_hashes)
        except Exception:
            log.exception("count priority stubs for progress")
            remaining = 0
    rem = int(remaining or 0)
    _STATE["account_stub_progress"] = {
        "active": active,
        "remaining": rem,
        "budget": rem,
        "done": int(done),
        "upgraded": int(upgraded),
        "still_stub": int(still_stub),
        "failed": int(failed),
        "skipped_prep": int(skipped_prep),
        "current_tid": current_tid,
        "current_title": (current_title or "")[:80],
    }


def account_stub_progress() -> dict[str, Any]:
    cur = _STATE.get("account_stub_progress")
    if isinstance(cur, dict) and cur:
        out = dict(cur)
        if "remaining" not in out and "budget" in out:
            out["remaining"] = out.get("budget") or 0
        return out
    return _empty_account_stub_progress(active=False)


_account_stub_task: Optional[asyncio.Task[Any]] = None
_account_stub_future: Any = None


def start_account_stub_recrawl() -> dict[str, Any]:
    """校验后后台跑账号爬占位（不限数量，直到队列清空或本轮均已尝试）。"""
    global _account_stub_task, _account_stub_future
    from workers.crawl_executor import spawn_crawl

    st = crawl_status()
    if st.get("looping") or st.get("running"):
        return {
            "ok": False,
            "started": False,
            "reason": "busy" if st.get("running") else "loop_running",
            "error": "爬虫正在执行，请先停止后再账号爬占位",
        }
    if (
        (_account_stub_future is not None and not _account_stub_future.done())
        or (_account_stub_task is not None and not _account_stub_task.done())
    ):
        return {
            "ok": False,
            "started": False,
            "reason": "busy",
            "error": "账号爬占位正在进行中",
        }

    conn = connect()
    try:
        cfg = _load_crawler_cfg(conn)
        account_cookie = str(cfg.get("web_crawler_account_cookie") or "").strip()
        if not account_cookie:
            return {
                "ok": False,
                "started": False,
                "reason": "no_account_cookie",
                "error": "未配置账号 Cookie，请到论坛配置 → 进站 →「账号 Cookie」填写登录态",
            }
    finally:
        conn.close()

    rconn = connect_resource()
    try:
        stub_remaining = count_priority_account_stubs(rconn)
    finally:
        rconn.close()

    qconn = connect()
    try:
        discarded_remaining = _count_account_discarded(qconn)
    finally:
        qconn.close()

    remaining = int(stub_remaining) + int(discarded_remaining)
    if remaining <= 0:
        _log_activity("账号爬占位 · 无优先占位 / 未处理失败·无权跳过可处理")
        _publish_account_stub_progress(active=False, remaining=0)
        return {
            "ok": True,
            "started": False,
            "reason": "empty",
            "remaining": 0,
            "budget": 0,
            "stub_remaining": 0,
            "discarded_remaining": 0,
            "message": "无「优先占位」或「未处理失败 / 无阅读权限跳过」可处理",
        }

    _publish_account_stub_progress(active=True, remaining=remaining)

    async def _runner() -> None:
        global _account_stub_task
        _account_stub_task = asyncio.current_task()
        try:
            await recrawl_account_stubs()
        except Exception:
            log.exception("account stub background failed")
            try:
                rem = _db_priority_remaining()
            except Exception:
                rem = 0
            _publish_account_stub_progress(active=False, remaining=rem)
        finally:
            if _account_stub_task is asyncio.current_task():
                _account_stub_task = None

    _account_stub_future = spawn_crawl(_runner(), name="account-stubs")
    _log_activity(
        f"账号爬占位已启动 · 占位 {stub_remaining} · 未处理 {discarded_remaining} · 跑完为止"
    )
    return {
        "ok": True,
        "started": True,
        "remaining": remaining,
        "budget": remaining,
        "stub_remaining": int(stub_remaining),
        "discarded_remaining": int(discarded_remaining),
        "message": (
            f"已开始 · 占位 {stub_remaining} · 未处理失败/无权跳过 {discarded_remaining} · 直至重爬完"
        ),
    }


def _load_crawler_cfg(conn: Any) -> dict[str, Any]:
    configs = load_forum_configs_map(conn)
    cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
    proxy = get_setting(conn, "web_crawler_proxy", "")
    if proxy and not cfg.get("web_crawler_proxy"):
        cfg["web_crawler_proxy"] = proxy
    return cfg


def _resolve_item(resource_hash: str, cfg: dict[str, Any]) -> dict[str, Any]:
    rconn = connect_resource()
    try:
        item = get_resource_by_hash(rconn, resource_hash)
    finally:
        rconn.close()
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
    from parsers.boards import get_board_fid, get_board_policy

    pol = get_board_policy(board_fid_s)
    board_fid = get_board_fid(board_fid_s)
    if board_fid <= 0:
        return {"ok": False, "hash": resource_hash, "error": "缺少有效板块 fid，无法重爬"}
    stored_name = str(item.get("board_name") or "").strip()
    if stored_name and (" · " in stored_name or "-" in stored_name):
        board_name = stored_name.replace("-", " · ", 1) if " · " not in stored_name else stored_name
    else:
        board_name = pol.name
    title = str(item.get("title") or item.get("filename") or "")
    conn = connect()
    try:
        queued = requeue_for_recrawl(
            conn,
            url=source_url,
            board_fid=pol.key,
            board_name=board_name,
            title=title,
            forum_id=SITE_CRAWLER_FORUM_ID,
        )
    finally:
        conn.close()
    return {
        "ok": True,
        "hash": resource_hash,
        "tid": tid,
        "board_fid": pol.key,
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
        err_msg = str(outcome.get("outcome") or "retry")
        backoff = (
            3600
            if (
                outcome.get("soft_browser_retried")
                or "软文" in err_msg
                or "安全壳" in err_msg
            )
            else 900
        )
        mark_pending_retry(conn, thread_url, err_msg, backoff_seconds=backoff)
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
    board_fid = prepared["board_fid"]
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
    finally:
        conn.close()
    # 跳过/无效帖：清掉原占位行（如「提示信息」），否则重爬后仍挂在列表里
    if verdict == "skipped":
        is_stub = (prepared.get("link_kind") or "") == "stub" or str(
            prepared.get("ed2k_link") or ""
        ).lower().startswith("unavailable://")
        junk_title = not title_recognizable(title)
        if is_stub or junk_title:
            rconn = connect_resource()
            try:
                removed = delete_resource_by_hash(rconn, resource_hash) or delete_stub_by_source_url(
                    rconn, thread_url
                )
            finally:
                rconn.close()
            if removed:
                _log_activity(f"已入库重爬 · 删除无效占位 tid={tid}")

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
    finally:
        conn.close()

    prepared_list: list[dict[str, Any]] = []
    prep_errors: list[dict[str, Any]] = []
    for h in cleaned:
        prep = _resolve_item(h, cfg)
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
        # 上次「停止」会留下 stop 文件；不清理则 process_thread 条条直接 stopped
        THROTTLE.clear_stop()
        _log_activity(f"已入库批量重爬 · 开始 {len(prepared_list)} 条")
        session = session_from_config(cfg)
        await session.bootstrap()
        fetcher = fetcher_from_config(session, cfg)

        for i, prepared in enumerate(prepared_list):
            if THROTTLE.should_stop():
                _log_activity("已入库批量重爬 · 收到停止请求，中止后续")
                break
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


async def recrawl_account_stubs() -> dict[str, Any]:
    """用账号 Cookie 重爬优先占位，不限数量：每次从库取下一条，直至无可再试。

    本轮已尝试过的 hash（含仍占位）不再重复捞取，避免死循环；进度 remaining 每次查库。
    """
    st = crawl_status()
    if st.get("looping") or st.get("running"):
        _publish_account_stub_progress(active=False, remaining=_db_priority_remaining())
        return {
            "ok": False,
            "skipped": True,
            "reason": "busy" if st.get("running") else "loop_running",
            "error": "爬虫正在执行，请先停止后再账号爬占位",
            "processed": 0,
            "upgraded": 0,
            "still_stub": 0,
            "failed": 0,
        }

    conn = connect()
    try:
        cfg = _load_crawler_cfg(conn)
        account_cookie = str(cfg.get("web_crawler_account_cookie") or "").strip()
        if not account_cookie:
            _publish_account_stub_progress(active=False, remaining=0)
            return {
                "ok": False,
                "skipped": True,
                "reason": "no_account_cookie",
                "error": "未配置账号 Cookie，请到论坛配置 → 进站 →「账号 Cookie」填写登录态",
                "processed": 0,
                "upgraded": 0,
                "still_stub": 0,
                "failed": 0,
            }
    finally:
        conn.close()

    rconn = connect_resource()
    try:
        stub_remaining0 = count_priority_account_stubs(rconn)
    finally:
        rconn.close()
    qconn = connect()
    try:
        discarded_remaining0 = _count_account_discarded(qconn)
    finally:
        qconn.close()
    remaining0 = int(stub_remaining0) + int(discarded_remaining0)

    if remaining0 <= 0:
        _log_activity("账号爬占位 · 无优先占位 / 未处理失败·无权跳过可处理")
        _publish_account_stub_progress(active=False, remaining=0)
        return {
            "ok": True,
            "processed": 0,
            "upgraded": 0,
            "still_stub": 0,
            "failed": 0,
            "skipped_prep": 0,
            "items": [],
            "note": "无「优先占位」或「未处理失败 / 无阅读权限跳过」可处理",
        }

    lock = try_begin_exclusive("account_stubs")
    if not lock.get("ok"):
        _publish_account_stub_progress(active=False, remaining=remaining0)
        return {
            "ok": False,
            "skipped": True,
            "reason": lock.get("reason") or "busy",
            "error": lock.get("error") or "爬虫正在执行，请稍候",
            "processed": 0,
            "upgraded": 0,
            "still_stub": 0,
            "failed": 0,
        }

    session: Optional[SessionManager] = None
    items: list[dict[str, Any]] = []
    upgraded = 0
    still_stub = 0
    failed = 0
    skipped_prep = 0
    discarded_done = 0
    attempted: list[str] = []
    attempted_urls: list[str] = []

    def _push_progress(*, current_tid: int | None = None, current_title: str = "", active: bool = True) -> None:
        done = upgraded + still_stub + failed + skipped_prep
        _publish_account_stub_progress(
            active=active,
            remaining=None,  # 每次重新查库（占位 + 未处理跳过）
            done=done,
            upgraded=upgraded,
            still_stub=still_stub,
            failed=failed,
            skipped_prep=skipped_prep,
            current_tid=current_tid,
            current_title=current_title,
            exclude_hashes=None,
        )

    try:
        _log_activity(
            f"账号爬占位开始 · 占位 {stub_remaining0} · 未处理 {discarded_remaining0} · 登录 Cookie"
        )
        THROTTLE.clear_stop()
        _push_progress(active=True)
        session = session_from_config(
            cfg,
            cookie_override=account_cookie,
            account_jar=True,
        )
        await session.bootstrap()
        fetcher = fetcher_from_config(session, cfg)

        # ① 先用账号 Cookie 处理未处理：失败全部 → 无阅读权限跳过
        for disc_kind in ACCOUNT_DISCARDED_KINDS:
            kind_label = str(
                (DISCARDED_REQUEUE_KINDS.get(disc_kind) or {}).get("label") or disc_kind
            )
            _log_activity(f"账号爬未处理 · 开始类别「{kind_label}」")
            while True:
                if THROTTLE.should_stop():
                    _log_activity("账号爬占位 · 收到停止请求")
                    break

                qconn = connect()
                try:
                    batch = list_discarded_kind(
                        qconn,
                        disc_kind,
                        limit=1,
                        exclude_urls=attempted_urls,
                    )
                finally:
                    qconn.close()
                if not batch:
                    break

                row = batch[0]
                source_url = str(row.get("url") or "").strip()
                title = str(row.get("thread_title") or "")
                if source_url:
                    attempted_urls.append(source_url)

                tid = tid_from_url(source_url) or int(row.get("tid") or 0) or None
                if not tid:
                    skipped_prep += 1
                    discarded_done += 1
                    qconn = connect()
                    try:
                        mark_thread_skipped(qconn, source_url, f"{kind_label} · 无法解析 tid")
                    finally:
                        qconn.close()
                    _push_progress()
                    continue

                board_fid_s = str(row.get("board_fid") or "").strip() or str(
                    cfg.get("active_board_fid") or ""
                )
                board_fid = get_board_fid(board_fid_s)
                if board_fid <= 0:
                    skipped_prep += 1
                    discarded_done += 1
                    qconn = connect()
                    try:
                        mark_thread_skipped(qconn, source_url, f"{kind_label} · 缺少板块 fid")
                    finally:
                        qconn.close()
                    _push_progress(current_tid=int(tid), current_title=title)
                    continue

                pol = get_board_policy(board_fid_s)
                stored_name = str(row.get("board_name") or "").strip()
                if stored_name and (" · " in stored_name or "-" in stored_name):
                    board_name = (
                        stored_name.replace("-", " · ", 1)
                        if " · " not in stored_name
                        else stored_name
                    )
                else:
                    board_name = pol.name

                _push_progress(current_tid=int(tid), current_title=title)
                rem_now = int((_STATE.get("account_stub_progress") or {}).get("remaining") or 0)
                _log_activity(
                    f"账号爬未处理 · {kind_label} · tid={tid} · 剩 {rem_now} · {title[:36]}"
                )

                try:
                    outcome = await process_thread(
                        int(tid),
                        board_fid=pol.key,
                        board_name=board_name,
                        list_title=title,
                        persist=True,
                        crawler_config=cfg,
                        session=session,
                        fetcher=fetcher,
                        account_stub_pass=True,
                    )
                except Exception as exc:
                    log.exception("account discarded recrawl tid=%s kind=%s", tid, disc_kind)
                    failed += 1
                    discarded_done += 1
                    qconn = connect()
                    try:
                        mark_pending_retry(
                            qconn, source_url, str(exc)[:200], backoff_seconds=600
                        )
                    finally:
                        qconn.close()
                    _log_activity(f"账号爬未处理失败 · tid={tid} · {exc}")
                    _push_progress(current_tid=int(tid), current_title=title)
                    await asyncio.sleep(0.8)
                    continue

                verdict = str(outcome.get("verdict") or "failed")
                label = str(outcome.get("outcome") or outcome.get("verdict_label") or verdict)
                qconn = connect()
                try:
                    _apply_queue_outcome(qconn, source_url, outcome)
                finally:
                    qconn.close()
                discarded_done += 1
                if verdict == "import":
                    upgraded += 1
                    _log_activity(f"账号爬未处理升级 · tid={tid} · {label}")
                elif verdict == "stub":
                    still_stub += 1
                    _log_activity(f"账号爬未处理占位 · tid={tid} · {label}")
                elif verdict == "skipped":
                    skipped_prep += 1
                    _log_activity(f"账号爬未处理跳过 · tid={tid} · {label}")
                else:
                    failed += 1
                    _log_activity(f"账号爬未处理未升级 · tid={tid} · {label}")
                items.append(
                    {
                        "ok": verdict in {"import", "stub", "skipped"},
                        "source": "discarded",
                        "kind": disc_kind,
                        "upgraded": verdict == "import",
                        "still_stub": verdict == "stub",
                        "tid": int(tid),
                        "url": source_url,
                        "verdict": verdict,
                        "outcome": label,
                    }
                )
                _push_progress(current_tid=int(tid), current_title=title)
                await asyncio.sleep(0.35)

            if THROTTLE.should_stop():
                break

        # ② 再跑资源库优先占位
        while True:
            if THROTTLE.should_stop():
                _log_activity("账号爬占位 · 收到停止请求")
                break

            conn = connect_resource()
            try:
                batch = list_priority_account_stubs(
                    conn,
                    limit=1,
                    exclude_hashes=attempted,
                )
            finally:
                conn.close()
            if not batch:
                break

            row = batch[0]
            source_url = str(row.get("source_url") or "").strip()
            stub_hash = str(row.get("hash") or "").strip()
            title = str(row.get("title") or "")
            outcome_label = str(row.get("import_outcome") or "")
            if stub_hash:
                attempted.append(stub_hash)

            tid = tid_from_url(source_url)
            if not tid:
                skipped_prep += 1
                items.append(
                    {
                        "ok": False,
                        "hash": stub_hash,
                        "error": f"无法解析 tid：{source_url}",
                        "import_outcome": outcome_label,
                    }
                )
                _push_progress()
                continue

            board_fid_s = str(row.get("board_fid") or "").strip()
            if not board_fid_s:
                board_fid_s = str(cfg.get("active_board_fid") or "")
            board_fid = get_board_fid(board_fid_s)
            if board_fid <= 0:
                skipped_prep += 1
                items.append(
                    {
                        "ok": False,
                        "hash": stub_hash,
                        "tid": tid,
                        "error": "缺少有效板块 fid",
                        "import_outcome": outcome_label,
                    }
                )
                _push_progress(current_tid=tid, current_title=title)
                continue

            pol = get_board_policy(board_fid_s)
            stored_name = str(row.get("board_name") or "").strip()
            if stored_name and (" · " in stored_name or "-" in stored_name):
                board_name = (
                    stored_name.replace("-", " · ", 1) if " · " not in stored_name else stored_name
                )
            else:
                board_name = pol.name
            _push_progress(current_tid=tid, current_title=title)
            rem_now = int((_STATE.get("account_stub_progress") or {}).get("remaining") or 0)
            _log_activity(
                f"账号爬占位 · tid={tid} · 剩 {rem_now} · {outcome_label[:24]} · {title[:36]}"
            )

            try:
                outcome = await process_thread(
                    tid,
                    board_fid=pol.key,
                    board_name=board_name,
                    list_title=title,
                    persist=True,
                    crawler_config=cfg,
                    session=session,
                    fetcher=fetcher,
                    account_stub_pass=True,
                )
            except Exception as exc:
                log.exception("account stub recrawl tid=%s", tid)
                failed += 1
                items.append(
                    {
                        "ok": False,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "error": str(exc),
                        "import_outcome": outcome_label,
                    }
                )
                _log_activity(f"账号爬占位失败 · tid={tid} · {exc}")
                _push_progress(current_tid=tid, current_title=title)
                await asyncio.sleep(0.8)
                continue

            verdict = str(outcome.get("verdict") or "failed")
            label = str(outcome.get("outcome") or outcome.get("verdict_label") or verdict)

            if verdict == "import":
                conn = connect_resource()
                try:
                    removed = delete_stub_by_source_url(conn, source_url)
                finally:
                    conn.close()
                upgraded += 1
                _log_activity(
                    f"账号爬占位升级 · tid={tid} · {label}"
                    + (" · 已删旧占位" if removed else "")
                )
                items.append(
                    {
                        "ok": True,
                        "upgraded": True,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "verdict": verdict,
                        "outcome": label,
                        "stub_removed": removed,
                        "import_outcome": outcome_label,
                    }
                )
            elif verdict == "stub" and _is_reply_or_purchase_outcome(label):
                # 兜底：未走 account_stub_pass 时也不保留需回复/需购买占位
                conn = connect_resource()
                try:
                    removed = delete_stub_by_source_url(conn, source_url)
                finally:
                    conn.close()
                skipped_prep += 1
                items.append(
                    {
                        "ok": True,
                        "upgraded": False,
                        "skipped": True,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "verdict": "skipped",
                        "outcome": label,
                        "stub_removed": removed,
                        "import_outcome": outcome_label,
                    }
                )
                _log_activity(f"账号爬占位跳过 · tid={tid} · {label} · 已删占位")
            elif verdict == "stub":
                still_stub += 1
                items.append(
                    {
                        "ok": True,
                        "upgraded": False,
                        "still_stub": True,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "verdict": verdict,
                        "outcome": label,
                        "import_outcome": outcome_label,
                    }
                )
                _log_activity(f"账号爬占位仍占位 · tid={tid} · {label}")
            elif verdict == "skipped" and _is_reply_or_purchase_outcome(label):
                conn = connect_resource()
                try:
                    removed = delete_stub_by_source_url(conn, source_url)
                finally:
                    conn.close()
                skipped_prep += 1
                items.append(
                    {
                        "ok": True,
                        "upgraded": False,
                        "skipped": True,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "verdict": verdict,
                        "outcome": label,
                        "stub_removed": removed,
                        "import_outcome": outcome_label,
                    }
                )
                _log_activity(
                    f"账号爬占位跳过 · tid={tid} · {label}"
                    + (" · 已删旧占位" if removed else "")
                )
            else:
                failed += 1
                items.append(
                    {
                        "ok": False,
                        "upgraded": False,
                        "hash": stub_hash,
                        "tid": tid,
                        "url": source_url,
                        "verdict": verdict,
                        "outcome": label,
                        "import_outcome": outcome_label,
                        "error": label,
                    }
                )
                _log_activity(f"账号爬占位未升级 · tid={tid} · {label}")

            _push_progress(current_tid=tid, current_title=title)
            await asyncio.sleep(0.8)
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        _push_progress(active=False)
        end_exclusive()

    processed = upgraded + still_stub + failed + skipped_prep
    rem_left = _db_priority_remaining()
    _log_activity(
        f"账号爬占位结束 · 处理 {processed} · 升级 {upgraded} · 仍占位 {still_stub} · 失败 {failed}"
        + f" · 未处理已跑 {discarded_done}"
        + f" · 库内剩余 {rem_left}"
        + (f" · 跳过 {skipped_prep}" if skipped_prep else "")
    )
    return {
        "ok": True,
        "processed": processed,
        "upgraded": upgraded,
        "still_stub": still_stub,
        "failed": failed,
        "skipped_prep": skipped_prep,
        "discarded_done": discarded_done,
        "remaining": rem_left,
        "items": items,
        "note": "含优先占位 + 未处理失败 + 无阅读权限跳过；升级成功会删除旧占位",
    }


async def recrawl_discarded_tids(tids: list[int]) -> dict[str, Any]:
    """未处理明细批量重爬：按 tid 直接抓（不依赖当前活跃板队列）。

    - 连续调度中：只重新入队，由调度吃队列
    - 空闲：占用 running，共用会话顺序抓完，并写活动日志
    """
    clean: list[int] = []
    seen: set[int] = set()
    for raw in tids or []:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        clean.append(tid)
    if not clean:
        return {
            "ok": False,
            "error": "未提供有效 tid",
            "selected": 0,
            "requeued": 0,
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
        }

    conn = connect()
    try:
        cfg = _load_crawler_cfg(conn)
        rows = list_discarded_by_tids(conn, clean)
    finally:
        conn.close()

    if not rows:
        _log_activity(f"未处理批量重爬 · 选中 {len(clean)} · 无可重跑（可能已处理）")
        return {
            "ok": True,
            "mode": "noop",
            "selected": len(clean),
            "matched": 0,
            "requeued": 0,
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
            "note": "所选 tid 均不在失败/跳过队列（可能已处理）",
        }

    st = crawl_status()
    looping = bool(st.get("looping"))
    if looping:
        conn = connect()
        try:
            requeued = requeue_discarded_by_tids(conn, [int(r["tid"]) for r in rows])
        finally:
            conn.close()
        _log_activity(
            f"未处理批量重爬 · 入队 {requeued} 条（连续调度中）· 选中 {len(clean)}"
        )
        return {
            "ok": True,
            "mode": "queued",
            "selected": len(clean),
            "matched": len(rows),
            "requeued": requeued,
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "skipped": 0,
            "failed": 0,
            "items": [
                {
                    "ok": True,
                    "queued": True,
                    "tid": int(r.get("tid") or 0),
                    "url": r.get("url"),
                    "title": r.get("thread_title") or "",
                }
                for r in rows
            ],
            "note": f"连续调度进行中：已重新入队 {requeued} 条，由调度依次抓取",
        }

    lock = try_begin_exclusive("discarded_recrawl")
    if not lock.get("ok"):
        conn = connect()
        try:
            requeued = requeue_discarded_by_tids(conn, [int(r["tid"]) for r in rows])
        finally:
            conn.close()
        _log_activity(
            f"未处理批量重爬 · 爬虫忙 · 已入队 {requeued} 条 · 选中 {len(clean)}"
        )
        return {
            "ok": True,
            "mode": "queued",
            "selected": len(clean),
            "matched": len(rows),
            "requeued": requeued,
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
            "note": f"爬虫忙：已重新入队 {requeued} 条，空闲后由队列抓取",
            "reason": lock.get("reason") or "busy",
        }

    session: Optional[SessionManager] = None
    fetcher: Optional[Fetcher] = None
    items: list[dict[str, Any]] = []
    imports_n = 0
    stubs_n = 0
    skipped_n = 0
    failed_n = 0
    crawled_n = 0

    try:
        _log_activity(f"未处理批量重爬开始 · {len(rows)} 条")
        THROTTLE.clear_stop()
        session = session_from_config(cfg)
        await session.bootstrap()
        fetcher = fetcher_from_config(session, cfg)

        for i, row in enumerate(rows):
            if THROTTLE.should_stop():
                _log_activity("未处理批量重爬 · 收到停止请求")
                break

            thread_url = str(row.get("url") or "").strip()
            tid = int(row.get("tid") or tid_from_url(thread_url) or 0)
            title = str(row.get("thread_title") or "")
            board_key = str(row.get("board_fid") or "").strip() or str(
                cfg.get("active_board_fid") or ""
            )
            stored_name = str(row.get("board_name") or "").strip()
            pol = get_board_policy(board_key)
            if stored_name and (" · " in stored_name or "-" in stored_name):
                board_name = (
                    stored_name.replace("-", " · ", 1)
                    if " · " not in stored_name
                    else stored_name
                )
            else:
                board_name = pol.name

            if not tid or not thread_url:
                failed_n += 1
                items.append(
                    {
                        "ok": False,
                        "tid": tid or None,
                        "url": thread_url,
                        "error": "缺少 tid/url",
                    }
                )
                _log_activity("未处理重爬跳过 · 缺少 tid/url")
                continue

            _log_activity(f"未处理重爬 · tid={tid} · {title[:40]}")
            try:
                await THROTTLE.sleep()
                if THROTTLE.should_stop():
                    _log_activity("未处理批量重爬 · 收到停止请求")
                    break
                # 单帖上限，避免附件/浏览器挂死拖死整次「未处理重爬」与管理端
                try:
                    per_tid = float(
                        (cfg or {}).get("web_crawler_thread_timeout")
                        or os.getenv("WEB_CRAWLER_THREAD_TIMEOUT", "180")
                        or "180"
                    )
                except (TypeError, ValueError):
                    per_tid = 180.0
                per_tid = max(60.0, per_tid)
                outcome = await asyncio.wait_for(
                    process_thread(
                        tid,
                        board_fid=board_key,
                        board_name=board_name,
                        list_title=title,
                        persist=True,
                        crawler_config=cfg,
                        session=session,
                        fetcher=fetcher,
                    ),
                    timeout=per_tid,
                )
            except asyncio.TimeoutError:
                log.warning("discarded recrawl timeout tid=%s", tid)
                conn = connect()
                try:
                    mark_pending_retry(
                        conn,
                        thread_url,
                        f"单帖处理超时（>{int(per_tid)}s）",
                        backoff_seconds=600,
                    )
                finally:
                    conn.close()
                failed_n += 1
                crawled_n += 1
                items.append(
                    {
                        "ok": False,
                        "tid": tid,
                        "url": thread_url,
                        "title": title,
                        "error": f"单帖处理超时（>{int(per_tid)}s）",
                    }
                )
                _log_activity(f"未处理重爬超时 · tid={tid} · >{int(per_tid)}s")
                continue
            except Exception as exc:
                log.exception("discarded recrawl failed tid=%s", tid)
                conn = connect()
                try:
                    mark_pending_retry(conn, thread_url, str(exc)[:200], backoff_seconds=600)
                finally:
                    conn.close()
                failed_n += 1
                crawled_n += 1
                items.append(
                    {
                        "ok": False,
                        "tid": tid,
                        "url": thread_url,
                        "title": title,
                        "error": str(exc),
                    }
                )
                _log_activity(f"未处理重爬失败 · tid={tid} · {exc}")
                continue

            crawled_n += 1
            verdict = str(outcome.get("verdict") or "failed")
            label = str(outcome.get("verdict_label") or outcome.get("outcome") or verdict)
            conn = connect()
            try:
                _apply_queue_outcome(conn, thread_url, outcome)
            finally:
                conn.close()

            if verdict == "import":
                imports_n += 1
            elif verdict == "stub":
                stubs_n += 1
            elif verdict == "skipped":
                skipped_n += 1
            elif verdict in {"retry", "need_attachments"} or "软文" in str(
                outcome.get("outcome") or ""
            ):
                # 已回异常/待抓队列
                pass
            else:
                failed_n += 1

            items.append(
                {
                    "ok": verdict in _IMPORT_VERDICTS or verdict == "skipped",
                    "tid": tid,
                    "url": thread_url,
                    "title": title,
                    "verdict": verdict,
                    "label": label,
                }
            )
            _log_activity(f"未处理重爬 · tid={tid} · {label}")

            if i + 1 < len(rows):
                await asyncio.sleep(0.6)
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        end_exclusive()

    note = (
        f"已重爬 {crawled_n}/{len(rows)} · 入库 {imports_n} · 占位 {stubs_n}"
        f" · 跳过 {skipped_n} · 失败 {failed_n}"
    )
    _log_activity(f"未处理批量重爬结束 · {note}")
    return {
        "ok": imports_n > 0 or stubs_n > 0 or skipped_n > 0 or failed_n == 0,
        "mode": "immediate",
        "selected": len(clean),
        "matched": len(rows),
        "requeued": 0,
        "crawled": crawled_n,
        "imports": imports_n,
        "stubs": stubs_n,
        "skipped": skipped_n,
        "failed": failed_n,
        "items": items,
        "note": note,
    }
