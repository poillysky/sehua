from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth.config import auth_required, cookie_name
from auth.permissions import has_permission
from auth.tokens import decode_access_token


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip() or None
    return request.cookies.get(cookie_name())


def get_current_user(request: Request) -> dict | None:
    if not auth_required():
        return {
            "id": 0,
            "username": "local",
            "display_name": "本地模式",
            "roles": ["admin"],
            "is_active": True,
        }

    token = _extract_token(request)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    return {
        "id": int(payload["sub"]),
        "username": payload.get("username", ""),
        "roles": payload.get("roles", []),
        "is_active": True,
    }


def require_user(request: Request) -> dict:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


def require_permission(permission: str):
    def _checker(user: dict = Depends(require_user)) -> dict:
        if not has_permission(user.get("roles", []), permission):
            raise HTTPException(status_code=403, detail="权限不足")
        return user

    return _checker
