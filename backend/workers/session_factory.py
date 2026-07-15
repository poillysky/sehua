"""Build SessionManager / Fetcher from forum crawler config (+ site proxy)."""

from __future__ import annotations

from typing import Any

from crawler.fetcher import Fetcher
from crawler.list_urls import site_root
from crawler.session import DEFAULT_UA, SessionManager


def entry_urls_from_config(cfg: dict[str, Any]) -> list[str]:
    raw = str(cfg.get("web_crawl_urls") or "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def session_from_config(cfg: dict[str, Any], *, proxy: str = "") -> SessionManager:
    ua = str(cfg.get("web_crawler_ua") or "").strip() or DEFAULT_UA
    session = SessionManager(user_agent=ua, proxy=proxy)
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
