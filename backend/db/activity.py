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
                (level or "info")[:32],
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


def list_recent_activity(limit: int = 120) -> list[dict[str, Any]]:
    """返回 [{t, msg}]，最新在前；时间用本地时分秒。"""
    lim = max(1, min(int(limit or 120), 300))
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT created_at, message
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

    out: list[dict[str, Any]] = []
    for created_at, message in rows:
        msg = str(message or "").strip()
        if not msg:
            continue
        if hasattr(created_at, "strftime"):
            try:
                # 库内一般是 UTC；按本地墙钟显示更贴近操作感
                local = created_at
                if getattr(created_at, "tzinfo", None) is not None:
                    local = created_at.astimezone()
                t = local.strftime("%H:%M:%S")
            except Exception:
                t = time.strftime("%H:%M:%S")
        else:
            t = time.strftime("%H:%M:%S")
        out.append({"t": t, "msg": msg})
    return out
