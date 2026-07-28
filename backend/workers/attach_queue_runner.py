"""附件队列排水：每日定时 / 手动触发；命中日限即停，单日最多 50 帖。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from db.connection import connect
from db.forum_configs import load_forum_configs_map
from workers.attach_queue import (
    ATTACH_QUEUE_DAILY_CAP,
    ATTACH_QUEUE_FORUM_ID,
    ATTACH_QUEUE_OUTCOME,
    attach_queue_already_ran_today,
    attach_queue_schedule,
    attach_queue_status_snapshot,
    clear_attach_daily_limit_hit_if_stale,
    count_attach_queue,
    fetch_attach_queue,
    forum_uses_attach_daily_queue,
    is_attach_daily_limit_hit,
    is_attach_queue_scheduler_enabled,
    list_attach_queue_forums,
    mark_attach_daily_limit_hit,
    mark_attach_queue_ran,
    mark_thread_attach_queue,
)
from workers.pipeline import process_thread
from workers.session_factory import fetcher_from_config, session_from_config

log = logging.getLogger(__name__)

_SCHEDULER_TASK: asyncio.Task[None] | None = None
_RUNNING = False
_LAST_RESULT: dict[str, Any] = {}


def is_attach_queue_busy() -> bool:
    return bool(_RUNNING)


def last_attach_queue_result() -> dict[str, Any]:
    return dict(_LAST_RESULT or {})


def _log(msg: str) -> None:
    try:
        from workers.runner import _log_activity

        _log_activity(msg)
    except Exception:
        log.info(msg)


async def run_attach_queue_once(
    *,
    forum_id: str | None = None,
    limit: int = ATTACH_QUEUE_DAILY_CAP,
    trigger: str = "manual",
) -> dict[str, Any]:
    """排空附件队列（按论坛）。再次命中日限提示则停止，余票留队。"""
    global _RUNNING, _LAST_RESULT
    if _RUNNING:
        return {"ok": False, "error": "附件队列正在运行", "busy": True}
    _RUNNING = True
    lim = max(1, min(int(limit or ATTACH_QUEUE_DAILY_CAP), ATTACH_QUEUE_DAILY_CAP))
    summary: dict[str, Any] = {
        "ok": True,
        "trigger": trigger,
        "forums": [],
        "crawled": 0,
        "imports": 0,
        "stubs": 0,
        "queued_again": 0,
        "failed": 0,
        "skipped": 0,
        "stopped_on_limit": False,
        "remaining": 0,
    }
    try:
        conn = connect()
        try:
            raw = (forum_id or "").strip()
            if raw and not forum_uses_attach_daily_queue(raw):
                summary["ok"] = False
                summary["error"] = f"附件日限队列仅支持 {ATTACH_QUEUE_FORUM_ID}"
                _LAST_RESULT = summary
                return summary
            forums = (
                [ATTACH_QUEUE_FORUM_ID]
                if raw
                else list_attach_queue_forums(conn)
            )
        finally:
            conn.close()
        # 仅 2048
        forums = [f for f in forums if forum_uses_attach_daily_queue(f)]
        if not forums:
            summary["note"] = "附件队列为空（仅 2048）"
            _LAST_RESULT = summary
            return summary

        for fid in forums:
            clear_attach_daily_limit_hit_if_stale(fid)
            forum_res: dict[str, Any] = {
                "forum_id": fid,
                "crawled": 0,
                "imports": 0,
                "stubs": 0,
                "queued_again": 0,
                "failed": 0,
                "skipped": 0,
                "stopped_on_limit": False,
            }
            if is_attach_daily_limit_hit(fid):
                forum_res["stopped_on_limit"] = True
                forum_res["note"] = "当日已触日限，跳过本论坛"
                summary["stopped_on_limit"] = True
                summary["forums"].append(forum_res)
                continue

            conn = connect()
            try:
                rows = fetch_attach_queue(conn, forum_id=fid, limit=lim)
            finally:
                conn.close()
            if not rows:
                summary["forums"].append(forum_res)
                continue

            cfg_conn = connect()
            try:
                cfg = load_forum_configs_map(cfg_conn).get(fid) or {}
            finally:
                cfg_conn.close()

            session = session_from_config(cfg, forum_id=fid)
            fetcher = fetcher_from_config(session, cfg)
            try:
                await session.bootstrap()
                for row in rows:
                    tid = int(row.get("tid") or 0)
                    url = str(row.get("url") or "")
                    if not tid or not url:
                        continue
                    board_fid = str(row.get("board_fid") or "") or "103"
                    title = str(row.get("thread_title") or "")
                    try:
                        outcome = await process_thread(
                            tid,
                            board_fid=board_fid,
                            board_name=str(row.get("board_name") or ""),
                            session=session,
                            list_title=title,
                            persist=True,
                            crawler_config=cfg,
                            fetcher=fetcher,
                            preferred_link=None,
                            forum_id=fid,
                            replace_thread_assets=True,
                        )
                    except Exception as exc:
                        log.exception("attach queue tid=%s failed: %s", tid, exc)
                        forum_res["failed"] += 1
                        summary["failed"] += 1
                        continue

                    forum_res["crawled"] += 1
                    summary["crawled"] += 1
                    verdict = str(outcome.get("verdict") or "")
                    out_text = str(outcome.get("outcome") or "")

                    qconn = connect()
                    try:
                        from db.queue import mark_thread_done, mark_thread_skipped

                        if verdict == "attach_queued":
                            mark_attach_daily_limit_hit(fid)
                            mark_thread_attach_queue(
                                qconn, url, outcome=out_text or ATTACH_QUEUE_OUTCOME
                            )
                            forum_res["queued_again"] += 1
                            summary["queued_again"] += 1
                            forum_res["stopped_on_limit"] = True
                            summary["stopped_on_limit"] = True
                            _log(
                                f"附件队列 · {fid} tid={tid} 再触日限 · 停止本论坛排水"
                            )
                            break
                        if verdict == "import":
                            mark_thread_done(
                                qconn, url, outcome=out_text or "import"
                            )
                            forum_res["imports"] += 1
                            summary["imports"] += 1
                        elif verdict == "stub":
                            mark_thread_done(
                                qconn, url, outcome=out_text or "stub"
                            )
                            forum_res["stubs"] += 1
                            summary["stubs"] += 1
                        elif verdict == "skipped":
                            mark_thread_skipped(qconn, url, out_text or "skipped")
                            forum_res["skipped"] += 1
                            summary["skipped"] += 1
                        else:
                            # 失败/重试：仍留在附件队列，避免丢票
                            mark_thread_attach_queue(
                                qconn,
                                url,
                                outcome=out_text or f"附件队列未完成：{verdict}",
                            )
                            forum_res["failed"] += 1
                            summary["failed"] += 1
                    finally:
                        qconn.close()
            finally:
                await session.close()

            mark_attach_queue_ran(fid)
            summary["forums"].append(forum_res)

        conn = connect()
        try:
            summary["remaining"] = count_attach_queue(conn, forum_id=ATTACH_QUEUE_FORUM_ID)
        finally:
            conn.close()
        _log(
            f"附件队列排水完成 · 触发={trigger} · 抓{summary['crawled']} "
            f"入{summary['imports']} 占{summary['stubs']} "
            f"再入队{summary['queued_again']} 余{summary['remaining']}"
            + (" · 已触日限停" if summary["stopped_on_limit"] else "")
        )
        _LAST_RESULT = summary
        return summary
    except Exception as exc:
        log.exception("attach queue run failed")
        summary["ok"] = False
        summary["error"] = str(exc)
        _LAST_RESULT = summary
        return summary
    finally:
        _RUNNING = False


async def _scheduler_loop() -> None:
    while True:
        try:
            await asyncio.sleep(60)
            if not is_attach_queue_scheduler_enabled():
                continue
            if is_attach_queue_busy():
                continue
            hour, minute = attach_queue_schedule()
            now = datetime.now()
            if now.hour != hour or now.minute != minute:
                continue
            conn = connect()
            try:
                forums = list_attach_queue_forums(conn)
            finally:
                conn.close()
            if not forums:
                continue
            due = [
                f
                for f in forums
                if forum_uses_attach_daily_queue(f)
                and not attach_queue_already_ran_today(f)
            ]
            if not due:
                continue
            _log(f"定时附件队列触发 · {hour:02d}:{minute:02d} · 论坛 {','.join(due)}")
            await run_attach_queue_once(trigger="schedule")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("attach queue scheduler tick failed")


def start_attach_queue_scheduler() -> asyncio.Task[None]:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return _SCHEDULER_TASK
    _SCHEDULER_TASK = asyncio.get_running_loop().create_task(_scheduler_loop())
    return _SCHEDULER_TASK


async def stop_attach_queue_scheduler() -> None:
    global _SCHEDULER_TASK
    task = _SCHEDULER_TASK
    _SCHEDULER_TASK = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def attach_queue_progress() -> dict[str, Any]:
    snap = attach_queue_status_snapshot()
    snap["busy"] = is_attach_queue_busy()
    snap["last_result"] = last_attach_queue_result()
    return snap
