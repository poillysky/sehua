"""Build SessionManager / Fetcher from forum crawler config (+ site proxy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from crawler.fetcher import Fetcher
from crawler.list_urls import site_root
from crawler.session import COOKIE_FILE, DEFAULT_UA, SessionManager
from crawler.sites import get_site_adapter

# 账号爬占位专用 jar，避免与匿名会话互相覆盖
ACCOUNT_COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / "cookies_account.json"


def entry_urls_from_config(cfg: dict[str, Any]) -> list[str]:
    raw = str(cfg.get("web_crawl_urls") or "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def prioritize_preferred_entry(entries: list[str], preferred: str) -> list[str]:
    """把上次成功进站的 BBS 根提到最前；失效时仍可按原列表 failover。"""
    pref = (preferred or "").strip()
    if not pref:
        return list(entries or [])
    try:
        pref = site_root(pref)
    except Exception:
        pref = pref if pref.endswith("/") else pref + "/"

    out: list[str] = []
    seen: set[str] = set()

    def _push(u: str) -> None:
        u = (u or "").strip()
        if not u:
            return
        try:
            key = urlparse(u).netloc.lower().rstrip(".")
        except Exception:
            key = u.rstrip("/").lower()
        if not key or key in seen:
            return
        seen.add(key)
        out.append(u if u.endswith("/") or ".php" in urlparse(u).path.lower() else u + "/")

    _push(pref)
    for u in entries or []:
        _push(u)
    return out


def resolve_forum_entry_urls(
    cfg: dict[str, Any],
    forum_id: str = "",
    *,
    proxy: str = "",
) -> list[str]:
    """进站候选：2048 会把发布页解析成当日论坛线路（只解首个可用发布页）。

    若配置了 preferred_entry_url（上次成功 BBS），提到最前优先试。
    """
    urls = entry_urls_from_config(cfg)
    if not urls:
        preferred = str(cfg.get("preferred_entry_url") or "").strip()
        return prioritize_preferred_entry([], preferred) if preferred else []
    if (forum_id or "").strip() != "2048":
        return urls
    try:
        from crawler.publish_2048 import expand_2048_entry_urls

        ua = str(cfg.get("web_crawler_ua") or "").strip()
        headers = {"User-Agent": ua} if ua else None
        expanded = expand_2048_entry_urls(
            urls,
            headers=headers,
            proxy=proxy or "",
            resolve_jumps=False,
            max_publish_pages=1,
            max_entries=8,
            timeout=8.0,
        )
        entries = expanded or urls
    except Exception:
        entries = urls
    preferred = str(cfg.get("preferred_entry_url") or "").strip()
    return prioritize_preferred_entry(entries, preferred)


def session_from_config(
    cfg: dict[str, Any],
    *,
    proxy: str = "",
    cookie_override: Optional[str] = None,
    account_jar: bool = False,
    forum_id: str = "",
) -> SessionManager:
    """构建会话。

    cookie_override：显式 Cookie（账号批次传入）。
    account_jar=True：读写 cookies_account.json，与普通爬虫 jar 隔离。
    forum_id：选择站点适配器的 cookie 文件与域名。
    """
    adapter = get_site_adapter(forum_id)
    ua = str(cfg.get("web_crawler_ua") or "").strip() or DEFAULT_UA
    # 建会话不展开发布页（避免重复 HTTP / 卡住）；cookie 域进站后再按落地页刷新
    entries = entry_urls_from_config(cfg)
    entry0 = entries[0] if entries else ""
    if account_jar:
        cookie_file = ACCOUNT_COOKIE_FILE
    else:
        cookie_file = adapter.cookie_file()
    domains = adapter.cookie_domains(entry0)
    session = SessionManager(
        user_agent=ua,
        cookie_file=cookie_file,
        proxy=proxy,
        cookie_domains=domains,
    )
    if cookie_override is not None:
        cookie = str(cookie_override or "").strip()
    else:
        cookie = str(cfg.get("web_crawler_cookie") or "").strip()
    if cookie:
        session.apply_cookie_header(cookie)
    session.load()
    if cookie:
        session.apply_cookie_header(cookie)
    return session


def fetcher_from_config(
    session: SessionManager,
    cfg: dict[str, Any],
    *,
    proxy: str = "",
) -> Fetcher:
    timeout = float(cfg.get("web_crawler_timeout") or 30)
    return Fetcher(session, timeout=max(5.0, timeout), proxy=proxy or session.proxy)


def bootstrap_start_url(cfg: dict[str, Any], forum_id: str = "", *, proxy: str = "") -> str:
    # 仅取配置首条，不触发发布页展开
    urls = entry_urls_from_config(cfg)
    if not urls:
        return site_root("")
    return urls[0]


def bootstrap_probe_for_forum(cfg: dict[str, Any], forum_id: str = "", *, proxy: str = "") -> str:
    """探测 URL。2048 只给 thread.php 信号，真实探测在 bootstrap 按落地域重建。"""
    del proxy
    adapter = get_site_adapter(forum_id)
    if (forum_id or "").strip() == "2048":
        return adapter.bootstrap_probe_url("https://2048.local/")
    start = bootstrap_start_url(cfg, forum_id)
    root = site_root(start) if start else ""
    return adapter.bootstrap_probe_url(root or start)


def persist_preferred_entry_url(forum_id: str, entry_url: str) -> str:
    """进站成功后写入 preferred_entry_url（仅 2048）。"""
    if (forum_id or "").strip() != "2048":
        return ""
    if not (entry_url or "").strip():
        return ""
    try:
        from db.connection import connect
        from db.forum_configs import remember_preferred_entry_url

        conn = connect()
        try:
            return remember_preferred_entry_url(conn, forum_id, entry_url)
        finally:
            conn.close()
    except Exception:
        return ""
