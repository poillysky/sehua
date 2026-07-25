"""轻量 Postgres 连接池：close() 归还连接，兼容现有 conn.close() 调用。"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

log = logging.getLogger(__name__)

_LOCK = threading.Lock()
_POOLS: dict[str, Any] = {}


def _pool_max(env_key: str, default: int = 8) -> int:
    try:
        n = int(os.getenv(env_key, str(default)) or default)
    except (TypeError, ValueError):
        n = default
    return max(1, min(32, n))


class PooledConnection:
    """代理真实连接；close() 归还池，异常连接关闭丢弃。"""

    __slots__ = ("_pool", "_conn", "_closed")

    def __init__(self, pool: Any, conn: Any) -> None:
        object.__setattr__(self, "_pool", pool)
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_closed", False)

    def close(self) -> None:
        if self._closed:
            return
        object.__setattr__(self, "_closed", True)
        pool, conn = self._pool, self._conn
        try:
            if getattr(conn, "closed", 0):
                pool.putconn(conn, close=True)
                return
            try:
                conn.rollback()
            except Exception:
                try:
                    pool.putconn(conn, close=True)
                except Exception:
                    try:
                        conn.close()
                    except Exception:
                        pass
                return
            pool.putconn(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in PooledConnection.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self) -> "PooledConnection":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _pool_key(kwargs: dict[str, Any]) -> str:
    return (
        f"{kwargs.get('host')}:{kwargs.get('port')}/"
        f"{kwargs.get('dbname')}:{kwargs.get('user')}"
    )


def get_pooled_connection(
    kwargs: dict[str, Any],
    *,
    pool_name: str,
    maxconn_env: str = "POSTGRES_POOL_MAX",
    connect_fn: Callable[..., Any] | None = None,
) -> PooledConnection:
    """从命名池取连接；kwargs 变化时重建该池。"""
    import psycopg2
    from psycopg2 import pool as pg_pool

    key = f"{pool_name}|{_pool_key(kwargs)}"
    with _LOCK:
        existing = _POOLS.get(pool_name)
        if existing is not None and existing.get("key") != key:
            try:
                existing["pool"].closeall()
            except Exception:
                pass
            _POOLS.pop(pool_name, None)
            existing = None
        if existing is None:
            maxconn = _pool_max(maxconn_env, 8)
            dsn = dict(kwargs)
            dsn.setdefault("connect_timeout", 5)
            try:
                p = pg_pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=maxconn,
                    **dsn,
                )
            except Exception:
                # 池创建失败时退回直连（仍包一层，close 即真关）
                log.warning("连接池创建失败 · %s · 退回直连", pool_name, exc_info=True)
                raw = (connect_fn or psycopg2.connect)(**dsn)
                return _DirectClose(raw)
            _POOLS[pool_name] = {"key": key, "pool": p}
            existing = _POOLS[pool_name]
        p = existing["pool"]

    try:
        conn = p.getconn()
    except Exception:
        # 池耗尽或坏掉：直连兜底，避免整站卡死
        log.warning("连接池取连失败 · %s · 直连兜底", pool_name, exc_info=True)
        dsn = dict(kwargs)
        dsn.setdefault("connect_timeout", 5)
        return _DirectClose((connect_fn or psycopg2.connect)(**dsn))
    return PooledConnection(p, conn)


class _DirectClose:
    """无池时的薄包装，API 与 PooledConnection 一致。"""

    __slots__ = ("_conn",)

    def __init__(self, conn: Any) -> None:
        object.__setattr__(self, "_conn", conn)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _DirectClose.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self) -> "_DirectClose":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def close_pool(pool_name: str) -> None:
    with _LOCK:
        existing = _POOLS.pop(pool_name, None)
    if not existing:
        return
    try:
        existing["pool"].closeall()
    except Exception:
        pass


def close_all_pools() -> None:
    with _LOCK:
        names = list(_POOLS.keys())
    for name in names:
        close_pool(name)
