"""HTTP connectivity probe for forum entry URLs."""

from __future__ import annotations

import time

import httpx

DEFAULT_TEST_URL = "https://www.sehuatang.net/forum.php"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
CONNECT_TIMEOUT = 8.0
READ_TIMEOUT = 12.0


def test_http_link(
    test_url: str,
    *,
    proxy: str = "",
    cookie: str = "",
    user_agent: str = "",
    ok_message: str = "",
    fail_prefix: str = "访问失败",
) -> dict:
    proxy = (proxy or "").strip()
    url = (test_url or DEFAULT_TEST_URL).strip() or DEFAULT_TEST_URL
    ua = (user_agent or DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT

    headers = {
        "User-Agent": ua,
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if cookie.strip():
        headers["Cookie"] = cookie.strip()

    client_kwargs: dict = {
        "headers": headers,
        "timeout": httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        "follow_redirects": True,
    }
    if proxy:
        client_kwargs["proxy"] = proxy

    try:
        start = time.perf_counter()
        with httpx.Client(**client_kwargs) as client:
            response = client.get(url)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        ok = response.status_code < 500
        if ok:
            message = ok_message or ("代理联通正常" if proxy else "论坛链接联通正常")
        else:
            message = f"目标站点返回 HTTP {response.status_code}"
        return {
            "ok": ok,
            "message": message,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "test_url": url,
            "proxy": proxy,
            "proxy_used": bool(proxy),
            "final_url": str(response.url),
        }
    except httpx.HTTPError as exc:
        if proxy:
            message = f"{fail_prefix}（代理）：{exc}"
        else:
            message = f"{fail_prefix}：{exc}"
        return {
            "ok": False,
            "message": message,
            "status_code": None,
            "elapsed_ms": None,
            "test_url": url,
            "proxy": proxy,
            "proxy_used": bool(proxy),
            "final_url": None,
        }
