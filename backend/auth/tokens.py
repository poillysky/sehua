from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from auth.config import jwt_expire_hours, jwt_secret


def create_access_token(*, user_id: int, username: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "roles": roles,
        "iat": now,
        "exp": now + timedelta(hours=jwt_expire_hours()),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
