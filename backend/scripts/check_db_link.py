"""Check DB linkage vs ed2k schema."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db.connection as dbc


def main() -> None:
    print("env host:", os.getenv("POSTGRES_HOST"))
    print("dsn kwargs:", dbc.postgres_dsn_kwargs())

    dbc._mode = None
    try:
        conn = dbc.try_postgres()
        print("postgres: OK")
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY 1"
        )
        tables = [r[0] for r in cur.fetchall()]
        print("tables:", tables)
        for t in (
            "ed2k_resources",
            "resource_sources",
            "crawl_pages",
            "crawl_boards",
            "auth_users",
            "content_items",
            "assets",
        ):
            print(f"  {t}: {'YES' if t in tables else 'NO'}")
        conn.close()
    except Exception as e:
        print("postgres: FAIL", type(e).__name__, e)

    dbc._mode = None
    conn = dbc.connect_sqlite()
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1")
    print("sqlite tables:", [r[0] for r in cur.fetchall()])
    print("sqlite path:", dbc.sqlite_path())
    conn.close()

    mig = Path(r"E:\ed2k\database\migrations")
    if mig.is_dir():
        files = sorted(p.name for p in mig.glob("*.sql"))
        print("ed2k migrations on disk:", len(files), files[:5], "...")
    else:
        print("ed2k migrations: missing")

    print("sehuatang database/migrations:", (ROOT.parent / "database" / "migrations").exists())


if __name__ == "__main__":
    main()
