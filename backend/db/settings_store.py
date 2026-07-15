"""Key-value store on collector_settings (ed2k-aligned)."""

from __future__ import annotations

from typing import Any


def ensure_settings_table(conn: Any) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS collector_settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL DEFAULT '',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def load_settings_raw(conn: Any) -> dict[str, str]:
    ensure_settings_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM collector_settings")
    return {str(row[0]): str(row[1] if row[1] is not None else "") for row in cur.fetchall()}


def get_setting(conn: Any, key: str, default: str = "") -> str:
    ensure_settings_table(conn)
    cur = conn.cursor()
    cur.execute("SELECT value FROM collector_settings WHERE key = %s", (key,))
    row = cur.fetchone()
    if not row:
        return default
    return str(row[0] if row[0] is not None else default)


def set_setting(conn: Any, key: str, value: str) -> None:
    ensure_settings_table(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO collector_settings (key, value, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE
          SET value = EXCLUDED.value, updated_at = now()
        """,
        (key, value),
    )
    conn.commit()


def save_settings(conn: Any, updates: dict[str, str]) -> None:
    for key, value in updates.items():
        set_setting(conn, key, value)
