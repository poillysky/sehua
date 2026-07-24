from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from auth.config import auth_required, cookie_name, cookie_secure, jwt_expire_hours
from auth.deps import get_current_user, require_permission, require_user
from auth.passwords import verify_password
from auth.permissions import ROLE_PERMISSIONS, permissions_for_roles
from auth.repository import (
    count_users,
    create_user,
    delete_user,
    get_user_by_username,
    list_roles,
    list_users,
    touch_last_login,
    update_user,
)
from auth.tokens import create_access_token
from db.connection import connect

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class CreateUserBody(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = None
    roles: list[str] = Field(default_factory=lambda: ["viewer"])


class UpdateUserBody(BaseModel):
    display_name: str | None = None
    password: str | None = Field(default=None, min_length=6, max_length=128)
    is_active: bool | None = None
    roles: list[str] | None = None


class ChangePasswordBody(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=6, max_length=128)


def _client_facing_https(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto == "https":
        return True
    if proto == "http":
        return False
    for key in ("origin", "referer"):
        val = (request.headers.get(key) or "").strip().lower()
        if val.startswith("https://"):
            return True
    return (request.url.scheme or "").lower() == "https"


def _set_auth_cookie(response: Response, token: str, request: Request | None = None) -> None:
    # 反代 HTTPS（如 clawer.xxx:16666）时打 Secure，减轻 iOS 主屏幕全屏丢 Cookie
    secure = cookie_secure()
    if request is not None and _client_facing_https(request):
        secure = True
    response.set_cookie(
        key=cookie_name(),
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=jwt_expire_hours() * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=cookie_name(), path="/")


def _user_payload(user) -> dict:
    roles = user.roles if hasattr(user, "roles") else user.get("roles", [])
    return {
        "id": user.id if hasattr(user, "id") else user.get("id"),
        "username": user.username if hasattr(user, "username") else user.get("username"),
        "display_name": user.display_name if hasattr(user, "display_name") else user.get("display_name"),
        "roles": roles,
        "permissions": sorted(permissions_for_roles(roles)),
        "is_active": user.is_active if hasattr(user, "is_active") else user.get("is_active", True),
    }


@router.get("/status")
def auth_status(request: Request) -> dict:
    user = get_current_user(request)
    has_users = False
    if auth_required():
        conn = connect()
        try:
            has_users = count_users(conn) > 0
        finally:
            conn.close()
    return {
        "auth_required": auth_required(),
        "authenticated": user is not None,
        "has_users": has_users,
        "user": _user_payload(user) if user else None,
        "roles": list(ROLE_PERMISSIONS.keys()),
    }


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    conn = connect()
    try:
        found = get_user_by_username(conn, body.username.strip())
        if not found:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        user, password_hash = found
        if not user.is_active:
            raise HTTPException(status_code=403, detail="账号已禁用")
        if not verify_password(body.password, password_hash):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        token = create_access_token(
            user_id=user.id,
            username=user.username,
            roles=user.roles,
        )
        touch_last_login(conn, user.id)
        _set_auth_cookie(response, token, request)
        return {"message": "success", "token": token, "user": _user_payload(user)}
    finally:
        conn.close()


@router.post("/logout")
def logout(response: Response) -> dict:
    _clear_auth_cookie(response)
    return {"message": "success"}


@router.get("/me")
def me(user: dict = Depends(require_user)) -> dict:
    conn = connect()
    try:
        from auth.repository import get_user_by_id

        db_user = get_user_by_id(conn, user["id"])
        if not db_user:
            raise HTTPException(status_code=401, detail="用户不存在")
        return {"user": _user_payload(db_user)}
    finally:
        conn.close()


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    user: dict = Depends(require_user),
) -> dict:
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")

    conn = connect()
    try:
        found = get_user_by_username(conn, user["username"])
        if not found:
            raise HTTPException(status_code=401, detail="用户不存在")
        db_user, password_hash = found
        if int(db_user.id) != int(user["id"]):
            raise HTTPException(status_code=401, detail="用户不存在")
        if not verify_password(body.current_password, password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")

        updated = update_user(conn, db_user.id, password=body.new_password)
        if not updated:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"message": "密码已修改"}
    finally:
        conn.close()


@router.get("/roles")
def roles_api(_user: dict = Depends(require_permission("users.manage"))) -> dict:
    conn = connect()
    try:
        return {"roles": list_roles(conn)}
    finally:
        conn.close()


@router.get("/users")
def users_api(_user: dict = Depends(require_permission("users.manage"))) -> dict:
    conn = connect()
    try:
        return {"users": list_users(conn), "roles": list_roles(conn)}
    finally:
        conn.close()


@router.post("/users")
def create_user_api(
    body: CreateUserBody,
    _user: dict = Depends(require_permission("users.manage")),
) -> dict:
    conn = connect()
    try:
        user = create_user(
            conn,
            username=body.username.strip(),
            password=body.password,
            display_name=(body.display_name or body.username).strip(),
            roles=body.roles or ["viewer"],
        )
        return {"message": "success", "user": _user_payload(user)}
    except Exception as exc:
        conn.rollback()
        if "auth_users_username_key" in str(exc):
            raise HTTPException(status_code=400, detail="用户名已存在") from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.put("/users/{user_id}")
def update_user_api(
    user_id: int,
    body: UpdateUserBody,
    current: dict = Depends(require_permission("users.manage")),
) -> dict:
    if user_id == current["id"] and body.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用当前登录账号")

    conn = connect()
    try:
        user = update_user(
            conn,
            user_id,
            display_name=body.display_name,
            password=body.password,
            is_active=body.is_active,
            roles=body.roles,
        )
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"message": "success", "user": _user_payload(user)}
    except ValueError as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()


@router.delete("/users/{user_id}")
def delete_user_api(
    user_id: int,
    current: dict = Depends(require_permission("users.manage")),
) -> dict:
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")

    conn = connect()
    try:
        if not delete_user(conn, user_id):
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"message": "success"}
    finally:
        conn.close()
