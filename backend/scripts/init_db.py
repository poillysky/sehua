#!/usr/bin/env python3
"""Ensure Postgres DB exists and apply ed2k-align migration."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:
    print("pip install psycopg2-binary")
    raise SystemExit(1)

from db.connection import postgres_dsn_kwargs
from db.migrate import ensure_ed2k_schema, run_migrations
from db.repository import get_data_overview
from db.connection import try_postgres


def ensure_database() -> None:
    kw = postgres_dsn_kwargs()
    db = kw["dbname"]
    conn = psycopg2.connect(
        host=kw["host"],
        port=kw["port"],
        user=kw["user"],
        password=kw["password"],
        dbname="postgres",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{db}"')
            print(f"created database {db}")
        else:
            print(f"database {db} already exists")
    conn.close()


def main() -> int:
    ensure_database()
    ensure_ed2k_schema()
    # optional additive migrations that are IF NOT EXISTS safe after 014
    run_migrations(only={"002_collector_settings.sql", "004_discuz_crawler_settings.sql"})
    conn = try_postgres()
    try:
        overview = get_data_overview(conn)
    finally:
        conn.close()
    print("overview:", overview)
    print("ed2k align OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
