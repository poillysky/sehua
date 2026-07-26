"""爬虫活动日志：落库，供活动页在 reload 后仍可读。"""

from __future__ import annotations

import logging
import time
from typing import Any

from db.connection import connect

log = logging.getLogger(__name__)

_KEEP = 500
_RUN_ID = f"live-{int(time.time())}"


def append_activity(
    message: str,
    *,
    level: str = "info",
    board_fid: str | None = None,
    board_name: str | None = None,
    thread_url: str | None = None,
    thread_title: str | None = None,
    run_id: str | None = None,
) -> None:
    msg = (message or "").strip()
    if not msg:
        return
    rid = (run_id or _RUN_ID).strip() or "live"
    resolved_level = (level or "info").strip() or "info"
    if resolved_level == "info":
        resolved_level = infer_activity_level(msg)
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO crawl_activity_log (
              run_id, level, message, board_fid, board_name, thread_url, thread_title
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                rid,
                resolved_level[:32],
                msg[:2000],
                (board_fid or None),
                (board_name or None),
                (thread_url or None),
                (thread_title or None),
            ),
        )
        # 偶发清理，避免表无限涨
        if abs(hash(msg)) % 37 == 0:
            cur.execute(
                """
                DELETE FROM crawl_activity_log
                WHERE id < COALESCE(
                  (SELECT id FROM crawl_activity_log ORDER BY id DESC OFFSET %s LIMIT 1),
                  0
                )
                """,
                [_KEEP],
            )
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        log.debug("append_activity failed: %s", exc)
    finally:
        conn.close()


def infer_activity_level(message: str) -> str:
    msg = message or ""
    if "风控熔断" in msg or "熔断" in msg:
        return "error"
    if any(x in msg for x in ("失败", "异常", "错误", "超时")):
        return "error"
    if any(x in msg for x in ("跳过", "保留重试", "待重试", "需登录", "停板", "取消", "停止")):
        return "warn"
    if any(x in msg for x in ("正常入库", "占位入库", "成功", "进站就绪", "已启动")):
        return "success"
    return "info"


def _row_to_activity(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        row_id,
        created_at,
        level,
        message,
        board_fid,
        board_name,
        thread_url,
        thread_title,
    ) = row
    msg = str(message or "").strip()
    lvl = str(level or "info").strip() or "info"
    if lvl == "info":
        lvl = infer_activity_level(msg)
    if hasattr(created_at, "strftime"):
        try:
            local = created_at
            if getattr(created_at, "tzinfo", None) is not None:
                local = created_at.astimezone()
            t = local.strftime("%H:%M:%S")
            created_iso = local.isoformat()
        except Exception:
            t = time.strftime("%H:%M:%S")
            created_iso = None
    else:
        t = time.strftime("%H:%M:%S")
        created_iso = str(created_at) if created_at else None
    return {
        "id": int(row_id or 0),
        "t": t,
        "msg": msg,
        "message": msg,
        "level": lvl,
        "created_at": created_iso,
        "board_fid": board_fid,
        "board_name": board_name,
        "thread_url": thread_url,
        "thread_title": thread_title,
    }


def list_recent_activity(limit: int = 120, *, since_id: int = 0) -> list[dict[str, Any]]:
    """返回活动行（新→旧）；含 id/level/message，兼容旧 {t,msg}。"""
    lim = max(1, min(int(limit or 120), 300))
    since = max(0, int(since_id or 0))
    conn = connect()
    try:
        cur = conn.cursor()
        if since > 0:
            cur.execute(
                """
                SELECT id, created_at, level, message,
                       board_fid, board_name, thread_url, thread_title
                FROM crawl_activity_log
                WHERE id > %s
                ORDER BY id DESC
                LIMIT %s
                """,
                [since, lim],
            )
        else:
            cur.execute(
                """
                SELECT id, created_at, level, message,
                       board_fid, board_name, thread_url, thread_title
                FROM crawl_activity_log
                ORDER BY id DESC
                LIMIT %s
                """,
                [lim],
            )
        rows = cur.fetchall() or []
    except Exception as exc:
        log.debug("list_recent_activity failed: %s", exc)
        return []
    finally:
        conn.close()

    return [_row_to_activity(r) for r in rows if str(r[3] or "").strip()]


def latest_activity_id() -> int:
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM crawl_activity_log")
        row = cur.fetchone()
        return int((row or [0])[0] or 0)
    except Exception:
        return 0
    finally:
        conn.close()


def persisted_rate_from_log(window_sec: int = 60) -> dict[str, int | float] | None:
    """按活动日志统计近 window 秒入库/占位，并折算成 /分。

    内存计数在进程重启后会丢，与面板日志不一致；以落库活动为准。
    """
    win = max(5, min(int(window_sec or 60), 600))
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*), MIN(created_at), MAX(created_at)
            FROM crawl_activity_log
            WHERE created_at >= now() - make_interval(secs => %s)
              AND (
                message LIKE '%%正常入库%%'
                OR message LIKE '%%占位入库%%'
                OR message LIKE '随机入库 %%'
              )
              AND message NOT LIKE '%%跳过已入库%%'
              AND message NOT LIKE '%%列表所见均已入库%%'
              AND message NOT LIKE '%%本批入库已达上限%%'
            """,
            [win],
        )
        row = cur.fetchone() or (0, None, None)
        raw = int(row[0] or 0)
        oldest = row[1]
        if raw <= 0 or oldest is None:
            return {"per_minute": 0, "window_sec": win, "raw_count": 0}
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        if getattr(oldest, "tzinfo", None) is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        else:
            oldest = oldest.astimezone(timezone.utc)
        span = max(3.0, (now - oldest).total_seconds())
        span = min(span, float(win))
        per_min = int(round(raw * 60.0 / span))
        return {
            "per_minute": max(0, per_min),
            "window_sec": win,
            "raw_count": raw,
        }
    except Exception as exc:
        log.debug("persisted_rate_from_log failed: %s", exc)
        return None
    finally:
        conn.close()


def clear_activity_log() -> int:
    """清空活动日志表；返回删除行数。"""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass(%s)", ("public.crawl_activity_log",))
        if cur.fetchone()[0] is None:
            return 0
        cur.execute("SELECT COUNT(*) FROM crawl_activity_log")
        n = int(cur.fetchone()[0] or 0)
        if n:
            cur.execute("DELETE FROM crawl_activity_log")
        conn.commit()
        return n
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        log.exception("clear_activity_log failed: %s", exc)
        raise
    finally:
        conn.close()
