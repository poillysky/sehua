"""PostgreSQL connection — prefer ed2k-aligned Postgres; SQLite only for auth fallback."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ENV = _BACKEND_ROOT / ".env"
load_dotenv(_ENV)

# PowerShell UTF-8 BOM: key may be \ufeffPOSTGRES_HOST
if not os.getenv("POSTGRES_HOST"):
    for key, value in os.environ.items():
        if key.lstrip("\ufeff") == "POSTGRES_HOST" and value:
            os.environ["POSTGRES_HOST"] = value
            break

_mode: str | None = None


def _auth_backend() -> str:
    return (os.getenv("AUTH_BACKEND", "postgres") or "postgres").strip().lower()


def postgres_dsn_kwargs() -> dict:
    timeout = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5") or "5")
    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "dbname": os.getenv("POSTGRES_DB", "ed2k"),
        "connect_timeout": max(1, timeout),
    }


def try_postgres():
    import psycopg2

    return psycopg2.connect(**postgres_dsn_kwargs())


def sqlite_path() -> Path:
    path = Path(os.getenv("AUTH_SQLITE_PATH", str(_BACKEND_ROOT / "data" / "auth.db")))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(str(sqlite_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def connection_mode() -> str:
    global _mode
    if _mode:
        return _mode
    return _auth_backend() if _auth_backend() != "auto" else "postgres"


def connect():
    """Postgres by default (ed2k schema). AUTH_BACKEND=sqlite|auto for fallback."""
    global _mode
    backend = _auth_backend()

    if backend == "sqlite":
        _mode = "sqlite"
        return connect_sqlite()

    if backend == "postgres":
        _mode = "postgres"
        return try_postgres()

    # auto
    try:
        conn = try_postgres()
        _mode = "postgres"
        return conn
    except Exception:
        _mode = "sqlite"
        return connect_sqlite()
