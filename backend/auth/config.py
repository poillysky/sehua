import os
import secrets

_cached_jwt_secret: str | None = None


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}


def jwt_secret() -> str:
    global _cached_jwt_secret
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret:
        return secret
    if _cached_jwt_secret is None:
        _cached_jwt_secret = secrets.token_urlsafe(48)
    return _cached_jwt_secret


def jwt_expire_hours() -> int:
    try:
        return max(1, min(int(os.getenv("JWT_EXPIRE_HOURS", "168")), 24 * 30))
    except ValueError:
        return 168


def cookie_name() -> str:
    return os.getenv("AUTH_COOKIE_NAME", "collector_token")


def cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"}


def initial_admin_username() -> str:
    return os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip()


def initial_admin_password() -> str:
    return os.getenv("INITIAL_ADMIN_PASSWORD", "admin123").strip()
