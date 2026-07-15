from __future__ import annotations

import logging

from auth.config import initial_admin_password, initial_admin_username
from auth.repository import count_users, create_user
from db.connection import connect

logger = logging.getLogger(__name__)


def ensure_initial_admin() -> None:
    username = initial_admin_username()
    password = initial_admin_password()
    if not username or not password:
        return

    conn = connect()
    try:
        if count_users(conn) > 0:
            return
        create_user(
            conn,
            username=username,
            password=password,
            display_name="管理员",
            roles=["admin"],
        )
        logger.info("已创建初始管理员账号: %s", username)
    finally:
        conn.close()


def warn_if_no_users() -> None:
    conn = connect()
    try:
        total = count_users(conn)
    finally:
        conn.close()
    if total == 0:
        logger.warning("尚未创建任何账号，将使用默认管理员自动初始化")
