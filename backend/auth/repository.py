"""Auth user/role repository — Postgres or SQLite."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from auth.passwords import hash_password
from db.connection import connection_mode


@dataclass
class AuthUser:
    id: int
    username: str
    display_name: str | None
    is_active: bool
    roles: list[str]


def _is_sqlite(conn) -> bool:
    return isinstance(conn, sqlite3.Connection) or connection_mode() == "sqlite"


def _execute(conn, sql: str, params: tuple | list = ()):
    if _is_sqlite(conn):
        return conn.execute(sql.replace("%s", "?"), params)
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur


def _commit(conn) -> None:
    conn.commit()


def get_user_roles(conn, user_id: int) -> list[str]:
    cur = _execute(
        conn,
        """
        SELECT r.name
        FROM auth_user_roles ur
        JOIN auth_roles r ON r.id = ur.role_id
        WHERE ur.user_id = %s
        ORDER BY r.name
        """,
        (user_id,),
    )
    return [row[0] for row in cur.fetchall()]


def get_user_by_username(conn, username: str) -> tuple[AuthUser, str] | None:
    cur = _execute(
        conn,
        """
        SELECT id, username, display_name, is_active, password_hash
        FROM auth_users
        WHERE username = %s
        """,
        (username,),
    )
    row = cur.fetchone()
    if not row:
        return None
    roles = get_user_roles(conn, row[0])
    user = AuthUser(
        id=int(row[0]),
        username=row[1],
        display_name=row[2],
        is_active=bool(row[3]),
        roles=roles,
    )
    return user, row[4]


def get_user_by_id(conn, user_id: int) -> AuthUser | None:
    cur = _execute(
        conn,
        """
        SELECT id, username, display_name, is_active
        FROM auth_users
        WHERE id = %s
        """,
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return None
    roles = get_user_roles(conn, row[0])
    return AuthUser(
        id=int(row[0]),
        username=row[1],
        display_name=row[2],
        is_active=bool(row[3]),
        roles=roles,
    )


def list_users(conn) -> list[dict]:
    cur = _execute(
        conn,
        """
        SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, u.last_login_at
        FROM auth_users u
        ORDER BY u.id
        """,
    )
    rows = cur.fetchall()
    users = []
    for row in rows:
        roles = get_user_roles(conn, row[0])
        created = row[4]
        last = row[5]
        users.append(
            {
                "id": int(row[0]),
                "username": row[1],
                "display_name": row[2],
                "is_active": bool(row[3]),
                "roles": roles,
                "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
                "last_login_at": last.isoformat() if hasattr(last, "isoformat") else last,
            }
        )
    return users


def list_roles(conn) -> list[dict]:
    cur = _execute(conn, "SELECT name, label, permissions FROM auth_roles ORDER BY id")
    out = []
    for row in cur.fetchall():
        perms = row[2]
        if isinstance(perms, str):
            perms = json.loads(perms)
        out.append({"name": row[0], "label": row[1], "permissions": list(perms or [])})
    return out


def count_users(conn) -> int:
    cur = _execute(conn, "SELECT COUNT(*) FROM auth_users")
    return int(cur.fetchone()[0])


def create_user(
    conn,
    *,
    username: str,
    password: str,
    display_name: str | None = None,
    roles: list[str] | None = None,
) -> AuthUser:
    roles = roles or ["viewer"]
    display = display_name or username
    pwd_hash = hash_password(password)

    if _is_sqlite(conn):
        cur = _execute(
            conn,
            """
            INSERT INTO auth_users (username, password_hash, display_name)
            VALUES (%s, %s, %s)
            """,
            (username, pwd_hash, display),
        )
        user_id = int(cur.lastrowid)
    else:
        cur = _execute(
            conn,
            """
            INSERT INTO auth_users (username, password_hash, display_name)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (username, pwd_hash, display),
        )
        user_id = int(cur.fetchone()[0])

    for role_name in roles:
        cur = _execute(conn, "SELECT id FROM auth_roles WHERE name = %s", (role_name,))
        role_row = cur.fetchone()
        if not role_row:
            raise ValueError(f"未知角色: {role_name}")
        _execute(
            conn,
            "INSERT INTO auth_user_roles (user_id, role_id) VALUES (%s, %s)",
            (user_id, role_row[0]),
        )
    _commit(conn)
    return AuthUser(
        id=user_id,
        username=username,
        display_name=display,
        is_active=True,
        roles=roles,
    )


def update_user(
    conn,
    user_id: int,
    *,
    display_name: str | None = None,
    password: str | None = None,
    is_active: bool | None = None,
    roles: list[str] | None = None,
) -> AuthUser | None:
    fields: list[str] = []
    params: list = []
    if display_name is not None:
        fields.append("display_name = %s")
        params.append(display_name)
    if password:
        fields.append("password_hash = %s")
        params.append(hash_password(password))
    if is_active is not None:
        fields.append("is_active = %s")
        if _is_sqlite(conn):
            params.append(1 if is_active else 0)
        else:
            params.append(is_active)

    if fields:
        params.append(user_id)
        _execute(conn, f"UPDATE auth_users SET {', '.join(fields)} WHERE id = %s", params)

    if roles is not None:
        _execute(conn, "DELETE FROM auth_user_roles WHERE user_id = %s", (user_id,))
        for role_name in roles:
            cur = _execute(conn, "SELECT id FROM auth_roles WHERE name = %s", (role_name,))
            role_row = cur.fetchone()
            if not role_row:
                raise ValueError(f"未知角色: {role_name}")
            _execute(
                conn,
                "INSERT INTO auth_user_roles (user_id, role_id) VALUES (%s, %s)",
                (user_id, role_row[0]),
            )
    _commit(conn)
    return get_user_by_id(conn, user_id)


def delete_user(conn, user_id: int) -> bool:
    cur = _execute(conn, "DELETE FROM auth_users WHERE id = %s", (user_id,))
    deleted = (cur.rowcount or 0) > 0
    _commit(conn)
    return deleted


def touch_last_login(conn, user_id: int) -> None:
    if _is_sqlite(conn):
        _execute(
            conn,
            "UPDATE auth_users SET last_login_at = datetime('now') WHERE id = %s",
            (user_id,),
        )
    else:
        _execute(conn, "UPDATE auth_users SET last_login_at = now() WHERE id = %s", (user_id,))
    _commit(conn)
