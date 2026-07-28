"""附件日限状态 + 附件队列（仅 2048；超额帖次日再跑）。

触发：2048 下载附件命中「今天下载…请明天再来」等日限提示。
行为：
  1. 当帖写入 crawl_pages.status=attach_queue
  2. 当日 2048 后续需附件帖：不下附件，直接入附件队列
  3. 每日定时（默认 01:05）排空 2048 附件队列；再次命中日限即停，余票留队
其他论坛不走此队列，日限提示仍按普通附件失败/无权处理。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from db.connection import connect
from db.settings_store import get_setting, set_setting

log = logging.getLogger(__name__)

# 附件日限队列仅针对 2048（站方 txt/附件日下载上限）
ATTACH_QUEUE_FORUM_ID = "2048"

ATTACH_QUEUE_STATUS = "attach_queue"
ATTACH_QUEUE_OUTCOME = "附件日限 · 已入附件队列"
ATTACH_QUEUE_VERDICT = "attach_queued"

# 单日附件队列最多尝试帖数（与站方 txt 日限对齐；命中日限提示会提前停）
ATTACH_QUEUE_DAILY_CAP = 50

_SETTING_HIT_DATE = "attach_daily_limit_hit_date:{forum_id}"
_SETTING_RUN_HOUR = "attach_queue_schedule_hour"
_SETTING_RUN_MINUTE = "attach_queue_schedule_minute"
_SETTING_LAST_RUN = "attach_queue_last_run_date:{forum_id}"
_SETTING_ENABLED = "attach_queue_scheduler_enabled"


def forum_uses_attach_daily_queue(forum_id: str | None) -> bool:
    """是否启用附件日限队列（仅 2048）。"""
    return (forum_id or "").strip() == ATTACH_QUEUE_FORUM_ID


def _today() -> str:
    return date.today().isoformat()


def _hit_key(forum_id: str) -> str:
    fid = (forum_id or ATTACH_QUEUE_FORUM_ID).strip() or ATTACH_QUEUE_FORUM_ID
    return _SETTING_HIT_DATE.format(forum_id=fid)


def _last_run_key(forum_id: str) -> str:
    fid = (forum_id or ATTACH_QUEUE_FORUM_ID).strip() or ATTACH_QUEUE_FORUM_ID
    return _SETTING_LAST_RUN.format(forum_id=fid)


def is_attach_daily_limit_hit(forum_id: str, *, today: str | None = None) -> bool:
    """当日该论坛是否已出现附件日限提示（非 2048 恒为 False）。"""
    if not forum_uses_attach_daily_queue(forum_id):
        return False
    day = today or _today()
    conn = connect()
    try:
        hit = (get_setting(conn, _hit_key(forum_id), "") or "").strip()
    finally:
        conn.close()
    return hit == day


def mark_attach_daily_limit_hit(forum_id: str, *, today: str | None = None) -> None:
    if not forum_uses_attach_daily_queue(forum_id):
        return
    day = today or _today()
    conn = connect()
    try:
        set_setting(conn, _hit_key(forum_id), day)
        conn.commit()
    finally:
        conn.close()
    log.info("attach daily limit hit forum=%s date=%s", forum_id, day)


def clear_attach_daily_limit_hit_if_stale(forum_id: str, *, today: str | None = None) -> None:
    """跨日清掉昨日日限标记（定时任务开头调用）。"""
    day = today or _today()
    conn = connect()
    try:
        hit = (get_setting(conn, _hit_key(forum_id), "") or "").strip()
        if hit and hit != day:
            set_setting(conn, _hit_key(forum_id), "")
            conn.commit()
            log.info("cleared stale attach daily limit forum=%s was=%s", forum_id, hit)
    finally:
        conn.close()


def attach_queue_schedule() -> tuple[int, int]:
    """定时跑附件队列的本地时:分。"""
    conn = connect()
    try:
        hour = int(get_setting(conn, _SETTING_RUN_HOUR, "1") or "1")
        minute = int(get_setting(conn, _SETTING_RUN_MINUTE, "5") or "5")
    finally:
        conn.close()
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return hour, minute


def is_attach_queue_scheduler_enabled() -> bool:
    conn = connect()
    try:
        raw = (get_setting(conn, _SETTING_ENABLED, "1") or "1").strip().lower()
    finally:
        conn.close()
    return raw not in {"0", "false", "no", "off"}


def mark_attach_queue_ran(forum_id: str, *, today: str | None = None) -> None:
    day = today or _today()
    conn = connect()
    try:
        set_setting(conn, _last_run_key(forum_id), day)
        conn.commit()
    finally:
        conn.close()


def attach_queue_already_ran_today(forum_id: str, *, today: str | None = None) -> bool:
    day = today or _today()
    conn = connect()
    try:
        last = (get_setting(conn, _last_run_key(forum_id), "") or "").strip()
    finally:
        conn.close()
    return last == day


def mark_thread_attach_queue(
    conn: Any,
    url: str,
    *,
    outcome: str = ATTACH_QUEUE_OUTCOME,
) -> None:
    """把帖子移入附件队列（连续调度不会取 status=attach_queue）。"""
    from db.queue import canonical_thread_url
    from parsers.safe_text import strip_nul

    url = canonical_thread_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE crawl_pages
        SET status = %s,
            outcome = %s,
            last_error = %s,
            retry_after = NULL,
            updated_at = now()
        WHERE page_type = 'thread' AND url = %s
        """,
        (
            ATTACH_QUEUE_STATUS,
            strip_nul(outcome or ATTACH_QUEUE_OUTCOME)[:200],
            "attachment_daily_limit",
            url,
        ),
    )
    conn.commit()


def count_attach_queue(conn: Any, *, forum_id: str | None = None) -> int:
    forum = (forum_id or "").strip()
    cur = conn.cursor()
    if forum:
        cur.execute(
            """
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread' AND status = %s AND forum_id = %s
            """,
            (ATTACH_QUEUE_STATUS, forum),
        )
    else:
        cur.execute(
            """
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread' AND status = %s
            """,
            (ATTACH_QUEUE_STATUS,),
        )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def list_attach_queue_forums(conn: Any) -> list[str]:
    """仅返回 2048（有积压时）；其他论坛的 attach_queue 行不参与排水。"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM crawl_pages
        WHERE page_type = 'thread' AND status = %s AND forum_id = %s
        """,
        (ATTACH_QUEUE_STATUS, ATTACH_QUEUE_FORUM_ID),
    )
    row = cur.fetchone()
    n = int(row[0] or 0) if row else 0
    return [ATTACH_QUEUE_FORUM_ID] if n > 0 else []


def fetch_attach_queue(
    conn: Any,
    *,
    forum_id: str,
    limit: int = ATTACH_QUEUE_DAILY_CAP,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), ATTACH_QUEUE_DAILY_CAP))
    forum = (forum_id or "").strip()
    if not forum_uses_attach_daily_queue(forum):
        return []
    forum = ATTACH_QUEUE_FORUM_ID
    cur = conn.cursor()
    cur.execute(
        """
        SELECT url, tid, thread_title, board_fid, board_name, forum_id,
               coalesce(outcome, ''), coalesce(fetch_fail_count, 0)
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = %s
          AND forum_id = %s
        ORDER BY updated_at ASC NULLS FIRST, id ASC
        LIMIT %s
        """,
        (ATTACH_QUEUE_STATUS, forum, lim),
    )
    rows = []
    for url, tid, title, board_fid, board_name, fid, outcome, fails in cur.fetchall():
        rows.append(
            {
                "url": url,
                "tid": tid,
                "thread_title": title or "",
                "board_fid": board_fid or "",
                "board_name": board_name or "",
                "forum_id": fid or forum,
                "outcome": outcome or "",
                "fetch_fail_count": int(fails or 0),
            }
        )
    return rows


def attach_queue_status_snapshot() -> dict[str, Any]:
    """管理端/状态接口用（仅 2048）。"""
    hour, minute = attach_queue_schedule()
    conn = connect()
    try:
        total = count_attach_queue(conn, forum_id=ATTACH_QUEUE_FORUM_ID)
        by_forum = {ATTACH_QUEUE_FORUM_ID: total}
        hits = {ATTACH_QUEUE_FORUM_ID: is_attach_daily_limit_hit(ATTACH_QUEUE_FORUM_ID)}
    finally:
        conn.close()
    return {
        "enabled": is_attach_queue_scheduler_enabled(),
        "forum_id": ATTACH_QUEUE_FORUM_ID,
        "schedule": f"{hour:02d}:{minute:02d}",
        "daily_cap": ATTACH_QUEUE_DAILY_CAP,
        "queued_total": total,
        "queued_by_forum": by_forum,
        "daily_limit_hit_today": hits,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }
