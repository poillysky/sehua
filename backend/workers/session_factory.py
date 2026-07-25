"""Build SessionManager / Fetcher from forum crawler config (+ site proxy)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from crawler.fetcher import Fetcher
from crawler.list_urls import site_root
from crawler.session import COOKIE_FILE, DEFAULT_UA, SessionManager
from crawler.sites import get_site_adapter

# 账号爬占位专用 jar，避免与匿名会话互相覆盖
ACCOUNT_COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / "cookies_account.json"


def entry_urls_from_config(cfg: dict[str, Any]) -> list[str]:
    raw = str(cfg.get("web_crawl_urls") or "")
    return [u.strip() for u in raw.split(",") if u.strip()]


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


def bootstrap_start_url(cfg: dict[str, Any]) -> str:
    urls = entry_urls_from_config(cfg)
    if not urls:
        return site_root("")
    return urls[0]


def bootstrap_probe_for_forum(cfg: dict[str, Any], forum_id: str = "") -> str:
    adapter = get_site_adapter(forum_id)
    start = bootstrap_start_url(cfg)
    root = site_root(start) if start else ""
    return adapter.bootstrap_probe_url(root or start)
