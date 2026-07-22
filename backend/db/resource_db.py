"""资源库独立连接：配置存在主库 collector_settings；未启用时回落主库。"""

from __future__ import annotations

import logging
import threading
from typing import Any

from db.connection import connect, postgres_dsn_kwargs, try_postgres
from db.settings_store import get_setting, save_settings

log = logging.getLogger(__name__)

SETTING_ENABLED = "resource_db_enabled"
SETTING_HOST = "resource_postgres_host"
SETTING_PORT = "resource_postgres_port"
SETTING_USER = "resource_postgres_user"
SETTING_PASSWORD = "resource_postgres_password"
SETTING_DB = "resource_postgres_db"

_CACHE_LOCK = threading.Lock()
_CACHED_KWARGS: dict[str, Any] | None = None
_CACHED_ENABLED: bool | None = None


def invalidate_resource_db_cache() -> None:
    global _CACHED_KWARGS, _CACHED_ENABLED
    with _CACHE_LOCK:
        _CACHED_KWARGS = None
        _CACHED_ENABLED = None


def primary_dsn_kwargs() -> dict[str, Any]:
    return dict(postgres_dsn_kwargs())


def _load_raw_from_primary() -> dict[str, str]:
    conn = connect()
    try:
        return {
            "enabled": get_setting(conn, SETTING_ENABLED, "false"),
            "host": get_setting(conn, SETTING_HOST, ""),
            "port": get_setting(conn, SETTING_PORT, ""),
            "user": get_setting(conn, SETTING_USER, ""),
            "password": get_setting(conn, SETTING_PASSWORD, ""),
            "dbname": get_setting(conn, SETTING_DB, ""),
        }
    finally:
        conn.close()


def resource_db_config(*, mask_password: bool = True) -> dict[str, Any]:
    """供管理端展示；未配置时回显主库连接信息（只读提示）。"""
    primary = primary_dsn_kwargs()
    raw = _load_raw_from_primary()
    enabled = str(raw.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"}
    host = (raw.get("host") or "").strip()
    port_s = (raw.get("port") or "").strip()
    user = (raw.get("user") or "").strip()
    password = raw.get("password") or ""
    dbname = (raw.get("dbname") or "").strip()
    configured = bool(enabled and host and dbname)

    try:
        port = int(port_s) if port_s else int(primary["port"])
    except (TypeError, ValueError):
        port = int(primary["port"])

    eff_host = host if configured else str(primary["host"])
    eff_user = user if configured else str(primary["user"])
    eff_db = dbname if configured else str(primary["dbname"])
    eff_port = port if configured else int(primary["port"])
    has_password = bool(password) if configured else bool(primary.get("password"))

    form_port: int | None
    if port_s.isdigit():
        form_port = int(port_s)
    elif enabled:
        form_port = int(primary["port"])
    else:
        form_port = None

    out: dict[str, Any] = {
        "enabled": enabled,
        "ready": configured,
        "using_primary": not configured,
        "host": host if enabled else "",
        "port": form_port,
        "user": user if enabled else "",
        "dbname": dbname if enabled else "",
        "has_password": bool(password) if enabled else False,
        "effective": {
            "host": eff_host,
            "port": eff_port,
            "user": eff_user,
            "dbname": eff_db,
            "has_password": has_password,
        },
        "primary": {
            "host": str(primary["host"]),
            "port": int(primary["port"]),
            "user": str(primary["user"]),
            "dbname": str(primary["dbname"]),
        },
    }
    if not mask_password and configured:
        out["password"] = password
    return out


def resource_dsn_kwargs() -> dict[str, Any]:
    """实际连接参数：启用且填齐时用独立库，否则主库。"""
    global _CACHED_KWARGS, _CACHED_ENABLED
    with _CACHE_LOCK:
        if _CACHED_KWARGS is not None and _CACHED_ENABLED is not None:
            return dict(_CACHED_KWARGS)

    primary = primary_dsn_kwargs()
    raw = _load_raw_from_primary()
    enabled = str(raw.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"}
    host = (raw.get("host") or "").strip()
    dbname = (raw.get("dbname") or "").strip()
    if not (enabled and host and dbname):
        kwargs = primary
        with _CACHE_LOCK:
            _CACHED_KWARGS = dict(kwargs)
            _CACHED_ENABLED = False
        return dict(kwargs)

    port_s = (raw.get("port") or "").strip()
    try:
        port = int(port_s) if port_s else int(primary["port"])
    except (TypeError, ValueError):
        port = int(primary["port"])
    user = (raw.get("user") or "").strip() or str(primary["user"])
    password = raw.get("password")
    if password is None or password == "":
        # 留空则沿用主库密码，便于同实例不同库名
        password = str(primary.get("password") or "")
    kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "dbname": dbname,
    }
    with _CACHE_LOCK:
        _CACHED_KWARGS = dict(kwargs)
        _CACHED_ENABLED = True
    return dict(kwargs)


def using_separate_resource_db() -> bool:
    resource_dsn_kwargs()
    with _CACHE_LOCK:
        return bool(_CACHED_ENABLED)


def connect_resource():
    """资源表读写连接。"""
    import psycopg2

    return psycopg2.connect(**resource_dsn_kwargs())


def open_resource_connection() -> tuple[Any | None, str | None]:
    """打开独立资源库连接。未启用独立库时返回 (None, None)。

    启用时连不上则 (None, error)。
    """
    if not using_separate_resource_db():
        return None, None
    try:
        return connect_resource(), None
    except Exception as exc:
        dsn = resource_dsn_kwargs()
        hint = (
            f"独立资源库连不上 {dsn.get('host')}:{dsn.get('port')}/{dsn.get('dbname')}：{exc}。"
            "跨 Docker 网络请填对方宿主机 IP（或 NAS IP）+ bridge 映射端口，"
            "不要填本 compose 内的服务名 postgres。"
        )
        return None, hint


def try_resource_postgres(kwargs: dict[str, Any] | None = None):
    import psycopg2

    return psycopg2.connect(**(kwargs or resource_dsn_kwargs()))


def save_resource_db_config(
    *,
    enabled: bool,
    host: str = "",
    port: int | None = None,
    user: str = "",
    password: str | None = None,
    dbname: str = "",
    keep_password: bool = False,
) -> dict[str, Any]:
    """写入主库设置；password=None 且 keep_password 时保留原密码。"""
    conn = connect()
    try:
        updates = {
            SETTING_ENABLED: "true" if enabled else "false",
            SETTING_HOST: (host or "").strip(),
            SETTING_PORT: str(int(port)) if port is not None else "",
            SETTING_USER: (user or "").strip(),
            SETTING_DB: (dbname or "").strip(),
        }
        if password is not None and str(password) != "":
            updates[SETTING_PASSWORD] = str(password)
        elif keep_password:
            pass
        elif not enabled:
            updates[SETTING_PASSWORD] = ""
        # password="" and not keep_password → 清空密码
        elif password is not None:
            updates[SETTING_PASSWORD] = ""
        save_settings(conn, updates)
    finally:
        conn.close()
    invalidate_resource_db_cache()
    return resource_db_config(mask_password=True)


def test_resource_db_connection(
    *,
    enabled: bool | None = None,
    host: str = "",
    port: int | None = None,
    user: str = "",
    password: str | None = None,
    dbname: str = "",
    use_saved_password: bool = False,
) -> dict[str, Any]:
    """探测连通性；不落库。"""
    primary = primary_dsn_kwargs()
    if enabled is False or (
        enabled is None and not using_separate_resource_db() and not (host or "").strip()
    ):
        # 测主库
        try:
            c = try_postgres()
            c.close()
            return {
                "ok": True,
                "using_primary": True,
                "message": f"主库连通 · {primary['host']}:{primary['port']}/{primary['dbname']}",
            }
        except Exception as exc:
            return {"ok": False, "using_primary": True, "message": str(exc)}

    raw = _load_raw_from_primary()
    h = (host or "").strip() or (raw.get("host") or "").strip()
    d = (dbname or "").strip() or (raw.get("dbname") or "").strip()
    u = (user or "").strip() or (raw.get("user") or "").strip() or str(primary["user"])
    if port is None:
        port_s = (raw.get("port") or "").strip()
        try:
            p = int(port_s) if port_s else int(primary["port"])
        except (TypeError, ValueError):
            p = int(primary["port"])
    else:
        p = int(port)

    if password is not None and password != "":
        pw = password
    elif use_saved_password or password is None:
        pw = raw.get("password") or str(primary.get("password") or "")
    else:
        pw = str(primary.get("password") or "")

    if not h or not d:
        return {"ok": False, "using_primary": False, "message": "请填写主机与数据库名"}

    kwargs = {"host": h, "port": p, "user": u, "password": pw, "dbname": d}
    try:
        c = try_resource_postgres(kwargs)
        try:
            cur = c.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            c.close()
        return {
            "ok": True,
            "using_primary": False,
            "message": f"资源库连通 · {h}:{p}/{d}",
        }
    except Exception as exc:
        return {"ok": False, "using_primary": False, "message": str(exc)}


def ensure_resource_schema() -> list[str]:
    """对当前资源库跑资源表迁移。"""
    from db.migrate import ensure_resource_db_schema

    conn = connect_resource()
    try:
        return ensure_resource_db_schema(conn)
    finally:
        conn.close()
