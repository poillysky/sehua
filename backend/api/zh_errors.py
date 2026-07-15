"""把后端异常转成管理端可读的中文提示。"""

from __future__ import annotations

import re
from typing import Any

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

# (子串匹配，中文提示)；按优先级从上到下
_PATTERNS: list[tuple[str, str]] = [
    ("notimplemented", "浏览器引擎无法启动（当前事件循环不支持启动子进程）。请重启后端后再试；若仍失败请执行 playwright install chromium"),
    ("browser bootstrap failed", "论坛进站失败：所有入口均未能完成浏览器初始化"),
    ("r18/safe shell", "仍卡在十八禁/安全浏览壳，无法进入论坛"),
    ("r18 block persists", "十八禁门拦截未解除，无法读取帖子"),
    ("cf challenge", "Cloudflare 人机验证未通过，请稍后重试或更换代理"),
    ("cf persists", "Cloudflare 验证持续存在，请稍后重试或更换代理"),
    ("cloudflare", "遇到 Cloudflare 防护，请稍后重试或更换代理"),
    ("empty page", "页面内容为空，可能被拦截或站点异常"),
    ("target closed", "浏览器会话已关闭，请重试"),
    ("browser has been closed", "浏览器会话已关闭，请重试"),
    ("executable doesn't exist", "未找到浏览器内核，请执行：playwright install chromium"),
    ("chromium", "浏览器相关错误，请确认已安装 Playwright Chromium"),
    ("timed out", "请求超时，请检查网络或代理后重试"),
    ("timeout", "请求超时，请检查网络或代理后重试"),
    ("connection refused", "连接被拒绝，请检查网络、入口域名或代理"),
    ("name or service not known", "域名解析失败，请检查入口域名或 DNS"),
    ("temporary failure in name resolution", "域名解析失败，请检查入口域名或 DNS"),
    ("getaddrinfo failed", "域名解析失败，请检查入口域名或 DNS"),
    ("ssl", "SSL/证书校验失败，请检查代理或站点证书"),
    ("certificate", "SSL/证书校验失败，请检查代理或站点证书"),
    ("proxy", "代理连接失败，请检查代理地址是否可用"),
    ("request failed", "请求失败，请检查网络或代理后重试"),
    ("connecterror", "网络连接失败，请检查网络或代理后重试"),
]


def _looks_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def localize_error_text(text: str, *, fallback: str = "操作失败，请稍后重试") -> str:
    raw = (text or "").strip()
    if not raw:
        return fallback
    if _looks_chinese(raw):
        return raw
    low = raw.lower()
    # 纯异常类名
    if low in {"notimplementederror", "notimplemented", "runtimeerror", "oserror", "error"}:
        if "notimplemented" in low:
            return _PATTERNS[0][1]
        return fallback
    for needle, zh in _PATTERNS:
        if needle in low:
            return zh
    # 保留简短英文便于排查，但加中文前缀
    if len(raw) <= 160 and re.fullmatch(r"[\w\s\-.:/\\()\[\]'\"=+?,!]+", raw):
        return f"解析失败：{raw}"
    return fallback


def user_facing_error(exc: BaseException, *, fallback: str = "操作失败，请稍后重试") -> str:
    """优先用异常文案，再按模式翻译；空 NotImplementedError 等也会落到中文。"""
    name = type(exc).__name__
    raw = str(exc).strip()
    if not raw:
        raw = name
    elif name and name.lower() not in raw.lower() and not _looks_chinese(raw):
        # 便于匹配 NotImplementedError 等
        raw = f"{name}: {raw}"
    return localize_error_text(raw, fallback=fallback)


def format_http_detail(detail: Any, *, fallback: str = "请求失败") -> str:
    """FastAPI detail（str / list / dict）→ 中文。"""
    if detail is None:
        return fallback
    if isinstance(detail, str):
        return localize_error_text(detail, fallback=fallback)
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = item.get("loc") or []
                field = ".".join(str(x) for x in loc if x != "body")
                msg = localize_error_text(str(item.get("msg") or ""), fallback="")
                if not msg:
                    continue
                parts.append(f"{field}：{msg}" if field else msg)
            else:
                parts.append(localize_error_text(str(item), fallback=str(item)))
        return "；".join(parts) if parts else fallback
    if isinstance(detail, dict):
        msg = detail.get("msg") or detail.get("message") or detail.get("detail")
        if msg:
            return localize_error_text(str(msg), fallback=fallback)
    return localize_error_text(str(detail), fallback=fallback)
