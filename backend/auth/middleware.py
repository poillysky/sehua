from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from auth.config import auth_required
from auth.deps import get_current_user
from auth.permissions import has_permission, route_permission


PUBLIC_PATHS = {
    "/health",
    "/login",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/status",
}

PUBLIC_PREFIXES = (
    "/static/",
)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        if not auth_required():
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return await call_next(request)

        user = get_current_user(request)
        if not user:
            # API / parse → JSON 401（便于管理前端处理）
            if path.startswith("/api/") or path.startswith("/parse/"):
                return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})
            if path == "/" or path.endswith(".html"):
                return RedirectResponse(url="/login", status_code=302)
            return JSONResponse(status_code=401, content={"detail": "未登录或登录已过期"})

        if path.startswith("/api/"):
            permission = route_permission(request.method, path)
            if permission and not has_permission(user.get("roles", []), permission):
                return JSONResponse(status_code=403, content={"detail": "权限不足"})

        return await call_next(request)
