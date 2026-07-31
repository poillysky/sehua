"""账号重爬每日额度（按论坛），避免账号 Cookie 单日请求过多被封。

配置：论坛 `web_crawler_account_stub_daily_limit`（默认 50；0=不限制）。
计数：settings 键 `account_stub_daily_used:{forum_id}` = `YYYY-MM-DD:N`。
只计实际发起抓帖的次数（调用 process_thread），不含本地跳过。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from db.connection import connect
from db.settings_store import get_setting, set_setting

DEFAULT_DAILY_LIMIT = 50
_SETTING_USED = "account_stub_daily_used:{forum_id}"


def _today() -> str:
    return date.today().isoformat()


def _used_key(forum_id: str) -> str:
    fid = (forum_id or "").strip() or "unknown"
    return _SETTING_USED.format(forum_id=fid)


def resolve_daily_limit(cfg: dict[str, Any] | None) -> int:
    """返回每日上限；0 表示不限制。"""
    raw = (cfg or {}).get("web_crawler_account_stub_daily_limit", DEFAULT_DAILY_LIMIT)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_DAILY_LIMIT
    return max(0, n)


def daily_used(forum_id: str, *, today: str | None = None) -> int:
    day = today or _today()
    conn = connect()
    try:
        raw = (get_setting(conn, _used_key(forum_id), "") or "").strip()
    finally:
        conn.close()
    if not raw:
        return 0
    if ":" not in raw:
        return 0
    d, _, rest = raw.partition(":")
    if d != day:
        return 0
    try:
        return max(0, int(rest or "0"))
    except ValueError:
        return 0


def note_daily_attempt(forum_id: str, *, today: str | None = None, n: int = 1) -> int:
    """记一次账号抓帖；返回当日累计。"""
    day = today or _today()
    add = max(1, int(n))
    conn = connect()
    try:
        key = _used_key(forum_id)
        raw = (get_setting(conn, key, "") or "").strip()
        used = 0
        if raw and ":" in raw:
            d, _, rest = raw.partition(":")
            if d == day:
                try:
                    used = max(0, int(rest or "0"))
                except ValueError:
                    used = 0
        used += add
        set_setting(conn, key, f"{day}:{used}")
        conn.commit()
        return used
    finally:
        conn.close()


def daily_remaining(forum_id: str, limit: int, *, today: str | None = None) -> int | None:
    """剩余可跑次数；limit=0 时返回 None（不限）。"""
    lim = max(0, int(limit))
    if lim <= 0:
        return None
    used = daily_used(forum_id, today=today)
    return max(0, lim - used)


def daily_status(forum_id: str, limit: int, *, today: str | None = None) -> dict[str, Any]:
    lim = max(0, int(limit))
    used = daily_used(forum_id, today=today)
    rem = None if lim <= 0 else max(0, lim - used)
    return {
        "limit": lim,
        "used": used,
        "remaining": rem,
        "unlimited": lim <= 0,
        "exhausted": bool(lim > 0 and used >= lim),
        "date": today or _today(),
    }
