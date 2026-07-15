"""Hybrid fetch: browser for age gate + list; fingerprint HTTP for threads.

Mode:
- list / forumdisplay / forum-*-*.html → Playwright (reuse session after 18+)
- thread / viewthread → curl_cffi HTTP with browser-synced cookies + safeid retry
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Literal, Optional
from urllib.parse import urlparse

from crawler.session import BASE_URL, SessionManager

log = logging.getLogger(__name__)

SAFEID_RE = re.compile(r"safeid\s*=\s*['\"]([^'\"]+)['\"]")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
CF_KEYWORDS = ("just a moment", "attention required", "challenge-platform")
CF_STATUS = {403, 429, 503}
IMPERSONATE = os.environ.get("SHT_CURL_IMPERSONATE", "chrome").strip() or "chrome"

FetchMode = Literal["auto", "browser", "http"]


class FetchError(Exception):
    pass


def detect_fetch_mode(url: str) -> Literal["browser", "http"]:
    """列表走浏览器，帖子走 HTTP。"""
    u = (url or "").lower()
    path = urlparse(url).path.lower() if url else ""
    if "viewthread" in u or "thread-" in path or "mod=viewthread" in u:
        return "http"
    if (
        "forumdisplay" in u
        or "forum-" in path
        or path.rstrip("/").endswith("forum.php")
        or "/forum.php" in u
    ):
        return "browser"
    # 默认保守：不明 URL 用浏览器（进站探测等）
    return "browser"


class Fetcher:
    """浏览器过十八禁 + 读列表；HTTP（指纹）读帖子。"""

    def __init__(
        self,
        session: SessionManager,
        timeout: float = 45.0,
        *,
        proxy: str = "",
    ):
        self.session = session
        self.timeout = timeout
        self.proxy = (proxy or getattr(session, "proxy", "") or "").strip()
        self._referer = f"{BASE_URL}forum.php"
        self._flaresolverr_url = (os.environ.get("SHT_FLARESOLVERR_URL") or "").strip() or None
        # 最近一次 get_thread_html 是否因软文/壳触发过浏览器整页重读
        self.last_soft_browser_retried: bool = False

    def set_referer(self, referer: str) -> None:
        self._referer = referer

    async def get_html(
        self,
        url: str,
        retry_r18: bool = True,
        retries: int = 3,
        *,
        mode: FetchMode = "auto",
    ) -> str:
        del retry_r18
        resolved: Literal["browser", "http"] = (
            detect_fetch_mode(url) if mode == "auto" else mode  # type: ignore[assignment]
        )
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                if resolved == "browser":
                    return await self._get_browser(url)
                return await self._get_http(url)
            except (FetchError, OSError, RuntimeError) as e:
                last_err = e
                log.warning(
                    "Request attempt %d/%d (%s) failed: %s",
                    attempt + 1,
                    retries,
                    resolved,
                    e,
                )
                if attempt + 1 < retries:
                    if resolved == "browser":
                        try:
                            await self.session.bootstrap(force=True)
                        except Exception as boot_err:
                            log.warning("Re-bootstrap failed: %s", boot_err)
                    await asyncio.sleep(2 * (attempt + 1))
        raise FetchError(str(last_err) if last_err else f"请求失败：{url}")

    async def get_list_html(self, url: str, retries: int = 3) -> str:
        return await self.get_html(url, retries=retries, mode="browser")

    async def get_thread_html(self, url: str, retries: int = 3) -> str:
        """HTTP 读帖；遇软文/安全壳自动浏览器整页重试一次。"""
        from parsers.thread_gates import is_safe_or_soft_shell

        self.last_soft_browser_retried = False
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                html = await self._get_http(url, raise_on_shell=False)
                if is_safe_or_soft_shell(html) or SessionManager.is_safe_shell(html):
                    log.info(
                        "Soft-ad/shell after HTTP, browser page retry (%s/%s): %s",
                        attempt + 1,
                        retries,
                        url,
                    )
                    html = await self._get_browser(url, raise_on_shell=False)
                    self.last_soft_browser_retried = True
                    if is_safe_or_soft_shell(html) or SessionManager.is_safe_shell(html):
                        log.warning("Still soft-ad/shell after browser retry: %s", url)
                    else:
                        log.info("Browser soft-retry recovered thread: %s", url)
                self._assert_usable_html(html, url, allow_soft=True)
                self.session.save()
                return html
            except (FetchError, OSError, RuntimeError) as e:
                last_err = e
                log.warning(
                    "Thread fetch attempt %d/%d failed: %s",
                    attempt + 1,
                    retries,
                    e,
                )
                if attempt + 1 < retries:
                    try:
                        await self.session.bootstrap(force=True)
                    except Exception as boot_err:
                        log.warning("Re-bootstrap failed: %s", boot_err)
                    await asyncio.sleep(2 * (attempt + 1))
        raise FetchError(str(last_err) if last_err else f"请求失败：{url}")

    async def _get_browser(self, url: str, *, raise_on_shell: bool = True) -> str:
        if not self.session._ready:
            await self.session.bootstrap()

        timeout_ms = int(max(self.timeout, 15) * 1000)
        html = await self.session.fetch_html(url, timeout_ms=timeout_ms)

        if self._is_cf_challenge(html):
            log.warning("Cloudflare in browser HTML, restarting session...")
            await self.session.bootstrap(force=True)
            html = await self.session.fetch_html(url, timeout_ms=timeout_ms)
            if self._is_cf_challenge(html):
                raise FetchError(f"Cloudflare 人机验证未通过：{url}")

        if raise_on_shell and SessionManager.is_safe_shell(html):
            raise FetchError(f"十八禁门拦截未解除：{url}")

        if raise_on_shell:
            self._assert_usable_html(html, url, allow_soft=False)
        return html

    async def _get_http(self, url: str, *, raise_on_shell: bool = True) -> str:
        if not self.session._ready:
            await self.session.bootstrap()

        # 优先：浏览器上下文内 HTTP（与列表同网络/代理，不整页导航）
        # 其次：curl_cffi 指纹 HTTP（环境直连正常时）
        html = ""
        try:
            html = await self._browser_api_get(url)
        except Exception as api_err:
            log.warning("Browser API HTTP failed, try curl_cffi: %s", api_err)
            try:
                html = await asyncio.to_thread(self._http_get, url)
            except Exception as curl_err:
                raise FetchError(f"HTTP 读帖失败: {curl_err}") from curl_err

        if self._is_cf_challenge(html):
            log.warning("Cloudflare challenge on thread %s", url)
            solved = await asyncio.to_thread(self._bypass_cf, url)
            if solved is None:
                try:
                    await self.session.fetch_html(self._referer or f"{BASE_URL}forum.php")
                    html = await self._browser_api_get(url)
                except Exception as exc:
                    raise FetchError(f"Cloudflare 验证持续存在：{url}") from exc
            else:
                html = solved

        if raise_on_shell and SessionManager.is_safe_shell(html):
            raise FetchError(f"十八禁门拦截未解除（安全标识重试后仍失败）：{url}")

        if raise_on_shell:
            self._assert_usable_html(html, url, allow_soft=False)

        self.session.save()
        return html

    def _assert_usable_html(self, html: str, url: str, *, allow_soft: bool) -> None:
        if allow_soft:
            if not html:
                raise FetchError(f"页面内容为空：{url}")
            return
        if SessionManager.is_safe_shell(html):
            raise FetchError(f"十八禁门拦截未解除：{url}")
        if "Powered by Discuz" not in html and len(html) < 5000:
            title = self._extract_title(html)
            raise FetchError(f"页面内容异常（标题={title!r}）：{url}")

    async def _browser_api_get(self, url: str) -> str:
        """浏览器页内 fetch 读帖（与 goto 同网络栈，非整页导航）。"""
        referer = self._referer or f"{BASE_URL}forum.php"

        async def _on_page(page: Any) -> str:
            async def _fetch_once() -> str:
                result = await page.evaluate(
                    """async ({ url, referer }) => {
                        const resp = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            redirect: 'follow',
                            headers: { 'Referer': referer },
                        });
                        return await resp.text();
                    }""",
                    {"url": url, "referer": referer},
                )
                return result or ""

            text = await _fetch_once()
            await self.session._sync_cookies_from_context()

            if self._is_r18_block(text):
                log.info("R18 shell on thread %s (page fetch), extract safeid and retry", url)
                if self._update_safeid(text):
                    await self.session._set_context_cookies(
                        {"_safe": self.session.cookies.get("_safe", ""), "safe": "1"}
                    )
                    text = await _fetch_once()
                    await self.session._sync_cookies_from_context()
            return text

        return await self.session.run_on_page(_on_page)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.session.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self._referer or f"{BASE_URL}forum.php",
        }

    def _cookie_dict(self) -> dict[str, str]:
        jar = dict(self.session.cookies)
        jar.setdefault("safe", "1")
        return {k: v for k, v in jar.items() if v}

    def _http_get(self, url: str) -> str:
        try:
            from curl_cffi import requests as crequests
        except ImportError as exc:
            raise FetchError("缺少 curl_cffi，请执行: pip install curl_cffi") from exc

        req_kwargs: dict = {
            "headers": self._headers(),
            "cookies": self._cookie_dict(),
            "allow_redirects": True,
            "timeout": min(self.timeout, 30),
            "impersonate": IMPERSONATE,
        }
        if self.proxy:
            req_kwargs["proxy"] = self.proxy
        try:
            r = crequests.get(url, **req_kwargs)
        except Exception as exc:
            raise FetchError(f"HTTP 请求失败: {exc}") from exc

        self._merge_response_cookies(r)
        text = self._decode_body(r)

        if self._is_cf_challenge_status(text, r.status_code):
            return text

        if self._is_r18_block(text):
            log.info("R18 shell on thread %s, extract safeid and retry", url)
            if not self._update_safeid(text):
                return text
            try:
                r2 = crequests.get(url, **req_kwargs)
            except Exception as exc:
                raise FetchError(f"R18 重试失败: {exc}") from exc
            self._merge_response_cookies(r2)
            text = self._decode_body(r2)
        return text

    def _merge_response_cookies(self, response) -> None:
        try:
            for name, value in (response.cookies or {}).items():
                if name and value:
                    self.session.cookies[name] = value
        except Exception:
            pass

    @staticmethod
    def _decode_body(response) -> str:
        body = response.content or b""
        if isinstance(body, (bytes, bytearray)):
            return body.decode(getattr(response, "encoding", None) or "utf-8", errors="replace")
        return str(body)

    def _update_safeid(self, html: str) -> bool:
        m = SAFEID_RE.search(html or "")
        if not m:
            return False
        self.session.update({"_safe": m.group(1), "safe": "1"})
        log.info("Wrote _safe from safeid")
        return True

    def _bypass_cf(self, url: str, max_retry: int = 2) -> Optional[str]:
        if not self._flaresolverr_url:
            log.warning("SHT_FLARESOLVERR_URL unset; cannot auto-bypass CF")
            return None
        try:
            from curl_cffi import requests as crequests
        except ImportError:
            return None

        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000,
            "cookies": [{"name": k, "value": v} for k, v in self._cookie_dict().items()],
        }
        try:
            r = crequests.post(
                self._flaresolverr_url,
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=90,
            )
            solution = (r.json() or {}).get("solution") or {}
            if solution.get("status") != 200:
                log.error("FlareSolverr bad status=%s", solution.get("status"))
                return None
            for c in solution.get("cookies") or []:
                name = str(c.get("name") or "").strip()
                value = c.get("value")
                if name and value is not None:
                    self.session.cookies[name] = str(value)
            ua = solution.get("userAgent")
            if ua:
                self.session.user_agent = ua
            html = solution.get("response") or ""
            if self._is_r18_block(html) and max_retry > 0:
                if self._update_safeid(html):
                    return self._bypass_cf(url, max_retry - 1)
            return html
        except Exception as e:
            log.error("FlareSolverr error: %s", e)
            return None

    @classmethod
    def _is_r18_block(cls, html: str) -> bool:
        if not html or len(html) > 12000:
            return False
        return "var safeid" in html

    def _is_cf_challenge(self, html: str) -> bool:
        return self._is_cf_challenge_status(html, 200)

    @staticmethod
    def _is_cf_challenge_status(html: str, status: int) -> bool:
        if status in CF_STATUS:
            return True
        lower = (html or "")[:8000].lower()
        title = Fetcher._extract_title(html).lower()
        return any(k in lower or k in title for k in CF_KEYWORDS)

    @staticmethod
    def _extract_title(html: str) -> str:
        m = TITLE_RE.search(html or "")
        if not m:
            return ""
        return re.sub(r"\s+", " ", m.group(1)).strip()
