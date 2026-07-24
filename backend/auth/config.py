import os
import secrets
from pathlib import Path

_cached_jwt_secret: str | None = None

# 与 backend 数据卷对齐：容器重建后仍能验签旧 Cookie，避免手机反复重登
_JWT_SECRET_FILE = Path(__file__).resolve().parents[1] / "data" / "jwt_secret"


def auth_required() -> bool:
    return os.getenv("AUTH_REQUIRED", "true").lower() in {"1", "true", "yes", "on"}


def jwt_secret() -> str:
    """登录令牌签名密钥。

    优先级：环境变量 JWT_SECRET → 数据目录持久文件 → 新生成并落盘。
    未持久化时每次进程重启密钥都会变，已登录设备会全部掉线。
    """
    global _cached_jwt_secret
    if _cached_jwt_secret:
        return _cached_jwt_secret

    env = os.getenv("JWT_SECRET", "").strip()
    if env:
        _cached_jwt_secret = env
        return _cached_jwt_secret

    try:
        if _JWT_SECRET_FILE.is_file():
            disk = _JWT_SECRET_FILE.read_text(encoding="utf-8").strip()
            if disk:
                _cached_jwt_secret = disk
                return _cached_jwt_secret
    except OSError:
        pass

    generated = secrets.token_urlsafe(48)
    try:
        _JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        _JWT_SECRET_FILE.write_text(generated, encoding="utf-8")
        try:
            os.chmod(_JWT_SECRET_FILE, 0o600)
        except OSError:
            pass
    except OSError:
        # 落盘失败仍用内存密钥，仅本进程有效
        pass
    _cached_jwt_secret = generated
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
