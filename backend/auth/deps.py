from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth.config import auth_required, cookie_name
from auth.permissions import has_permission
from auth.tokens import decode_access_token


def _extract_tokens(request: Request) -> list[str]:
    """按优先级收集候选令牌；Bearer 失效时仍应能回退到 Cookie。"""
    out: list[str] = []
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer = auth_header[7:].strip()
        if bearer:
            out.append(bearer)
    cookie = (request.cookies.get(cookie_name()) or "").strip()
    if cookie and cookie not in out:
        out.append(cookie)
    return out


def get_current_user(request: Request) -> dict | None:
    if not auth_required():
        return {
            "id": 0,
            "username": "local",
            "display_name": "本地模式",
            "roles": ["admin"],
            "is_active": True,
        }

    for token in _extract_tokens(request):
        payload = decode_access_token(token)
        if not payload:
            continue
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            continue
        return {
            "id": user_id,
            "username": payload.get("username", ""),
            "roles": payload.get("roles", []),
            "is_active": True,
        }
    return None


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
