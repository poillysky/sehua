"""Ensure auth_* tables — Postgres or SQLite."""

from __future__ import annotations

import logging

from db.connection import connect, connection_mode

logger = logging.getLogger(__name__)

_PG_SQL = """
CREATE TABLE IF NOT EXISTS auth_roles (
  id SERIAL PRIMARY KEY,
  name VARCHAR(32) NOT NULL UNIQUE,
  label VARCHAR(64) NOT NULL,
  permissions TEXT[] NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(64) NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name VARCHAR(128),
  is_active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS auth_user_roles (
  user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

INSERT INTO auth_roles (name, label, permissions) VALUES
  ('admin', '管理员', ARRAY['*']),
  ('operator', '操作员', ARRAY['resources.view', 'crawler.view', 'import', 'crawl.run', 'settings.read']),
  ('viewer', '只读', ARRAY['resources.view', 'crawler.view'])
ON CONFLICT (name) DO NOTHING;
"""

_SQLITE_SQL = """
CREATE TABLE IF NOT EXISTS auth_roles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  permissions TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS auth_user_roles (
  user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES auth_roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);
"""


def ensure_auth_schema() -> None:
    conn = connect()
    mode = connection_mode()
    try:
        if mode == "sqlite":
            conn.executescript(_SQLITE_SQL)
            cur = conn.execute("SELECT COUNT(*) FROM auth_roles")
            if int(cur.fetchone()[0]) == 0:
                conn.execute(
                    "INSERT INTO auth_roles (name, label, permissions) VALUES (?, ?, ?)",
                    ("admin", "管理员", '["*"]'),
                )
                conn.execute(
                    "INSERT INTO auth_roles (name, label, permissions) VALUES (?, ?, ?)",
                    (
                        "operator",
                        "操作员",
                        '["resources.view","crawler.view","import","crawl.run","settings.read"]',
                    ),
                )
                conn.execute(
                    "INSERT INTO auth_roles (name, label, permissions) VALUES (?, ?, ?)",
                    ("viewer", "只读", '["resources.view","crawler.view"]'),
                )
            conn.commit()
        else:
            with conn.cursor() as cur:
                cur.execute(_PG_SQL)
            conn.commit()
        logger.info("auth schema ready (%s)", mode)
    finally:
        conn.close()
