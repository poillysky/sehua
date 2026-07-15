"""Browser session for age gate + list pages; cookie jar for HTTP thread reads."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from crawler.pw_runtime import run_on_pw_loop

log = logging.getLogger(__name__)

BASE_URL = "https://www.sehuatang.net/"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
COOKIE_FILE = Path(__file__).resolve().parent.parent / "data" / "cookies.json"
COOKIE_DOMAINS = (".sehuatang.net", "www.sehuatang.net")


def _fmt_exc(exc: BaseException | None) -> str:
    if exc is None:
        return "未知错误"
    text = str(exc).strip()
    if isinstance(exc, NotImplementedError) or type(exc).__name__ == "NotImplementedError":
        return "浏览器无法在当前事件循环中启动（已自动切换独立循环，请重试）"
    return text or type(exc).__name__


class SessionManager:
    """浏览器过十八禁门并读列表；Cookie 同步后供 HTTP 读帖。

    Playwright 操作一律走独立 Proactor 循环，避免 Windows + uvicorn --reload
    使用 Selector 循环时无法 create_subprocess 的问题。
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        cookie_file: Path = COOKIE_FILE,
        *,
        proxy: str = "",
    ):
        self.user_agent = user_agent or DEFAULT_UA
        self.cookie_file = cookie_file
        self.proxy = (proxy or "").strip()
        self.cookies: dict[str, str] = {}
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._ready = False
        self.active_entry_url: str = BASE_URL

    def load(self) -> bool:
        if not self.cookie_file.exists():
            self.cookies.setdefault("safe", "1")
            return False
        try:
            data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
            self.cookies = {k: v for k, v in data.items() if v}
            self.cookies.setdefault("safe", "1")
            log.info("Loaded %d cookies from %s", len(self.cookies), self.cookie_file)
            return bool(self.cookies)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load cookies: %s", e)
            self.cookies.setdefault("safe", "1")
            return False

    def save(self) -> None:
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies.setdefault("safe", "1")
        self.cookie_file.write_text(
            json.dumps(self.cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("Saved cookies to %s", self.cookie_file)

    def update(self, cookies: dict[str, str]) -> None:
        for key, value in cookies.items():
            if value:
                self.cookies[key] = value
        self.cookies.setdefault("safe", "1")

    def apply_cookie_header(self, cookie_header: str) -> None:
        for part in (cookie_header or "").split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            key, value = key.strip(), value.strip()
            if key and value:
                self.cookies[key] = value
        self.cookies.setdefault("safe", "1")

    async def bootstrap(
        self,
        force: bool = False,
        *,
        start_url: str | None = None,
        probe_url: str | None = None,
        entry_urls: list[str] | None = None,
    ) -> dict[str, str]:
        """浏览器打开站点、过十八禁门；入口失效时按 entry_urls 顺序 failover。"""
        return await run_on_pw_loop(
            self._bootstrap_on_loop(
                force,
                start_url=start_url,
                probe_url=probe_url,
                entry_urls=entry_urls,
            )
        )

    async def _bootstrap_on_loop(
        self,
        force: bool = False,
        *,
        start_url: str | None = None,
        probe_url: str | None = None,
        entry_urls: list[str] | None = None,
    ) -> dict[str, str]:
        if force:
            await self._close_on_loop()
        elif self._ready and self._page:
            return self.cookies

        candidates: list[str] = []
        if start_url:
            candidates.append(start_url.strip())
        for u in entry_urls or []:
            u = (u or "").strip()
            if u and u not in candidates:
                candidates.append(u)
        if not candidates:
            candidates = [BASE_URL]

        self.load()
        last_err: Exception | None = None
        from crawler.list_urls import site_root

        for home in candidates:
            try:
                await self._close_on_loop()
                await self._ensure_browser()
                assert self._page
                page = self._page
                await page.goto(home, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                if await self._click_age_gate(page):
                    log.info("Age gate clicked (%s)", home)
                    await page.wait_for_timeout(3000)

                root = site_root(home)
                probe = (probe_url or f"{root}forum-2-1.html").strip()
                html = await self._fetch_html_on_loop(probe)
                if self.is_safe_shell(html):
                    raise RuntimeError(f"仍卡在十八禁/安全浏览壳，无法进入论坛：{home}")

                await self._sync_cookies_from_context()
                self._ready = True
                self.active_entry_url = home
                log.info(
                    "Browser session ready via %s cookies=%s",
                    home,
                    ",".join(sorted(self.cookies.keys())),
                )
                return self.cookies
            except Exception as exc:
                last_err = exc
                log.warning("Entry failover: %s failed: %s", home, _fmt_exc(exc))
                continue

        await self._close_on_loop()
        raise RuntimeError(f"论坛进站失败：所有入口均未能完成浏览器初始化（{_fmt_exc(last_err)}）")

    async def fetch_html(self, url: str, *, timeout_ms: int = 60000) -> str:
        """浏览器导航取 HTML（列表页主路径）。"""
        return await run_on_pw_loop(self._fetch_html_on_loop(url, timeout_ms=timeout_ms))

    async def _fetch_html_on_loop(self, url: str, *, timeout_ms: int = 60000) -> str:
        await self._ensure_browser()
        assert self._page
        page = self._page

        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(1500)

        html = await page.content()
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass

        if self._looks_like_age_gate(title, html):
            log.info("Age gate page detected for %s, clicking enter", url)
            if await self._click_age_gate(page):
                await page.wait_for_timeout(3000)
                html = await page.content()

        if self.is_safe_shell(html):
            for _ in range(6):
                await page.wait_for_timeout(1000)
                html = await page.content()
                if not self.is_safe_shell(html):
                    break
            if self.is_safe_shell(html):
                safeid = self._extract_safeid(html)
                if safeid:
                    await self._set_context_cookies({"_safe": safeid, "safe": "1"})
                    await page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
                    await page.wait_for_timeout(2000)
                    html = await page.content()

        await self._sync_cookies_from_context()
        return html

    async def close(self) -> None:
        await run_on_pw_loop(self._close_on_loop())

    async def _close_on_loop(self) -> None:
        self._ready = False
        for obj in (self._page, self._context, self._browser):
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception:
                pass
        self._page = None
        self._context = None
        self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None

    async def run_on_page(self, fn: Any) -> Any:
        """在浏览器循环上执行依赖当前 page 的协程工厂 `async def fn(page)`。"""

        async def _body() -> Any:
            await self._ensure_browser()
            assert self._page
            return await fn(self._page)

        return await run_on_pw_loop(_body())

    async def _ensure_browser(self) -> None:
        if self._page and self._context and self._browser:
            return

        log.info(
            "Launching Playwright chromium for sehuatang crawl%s...",
            f" proxy={self.proxy}" if self.proxy else "",
        )
        try:
            self._pw = await async_playwright().start()
            launch_kwargs: dict[str, Any] = {"headless": True}
            context_kwargs: dict[str, Any] = {
                "user_agent": self.user_agent,
                "locale": "zh-CN",
            }
            if self.proxy:
                context_kwargs["proxy"] = {"server": self.proxy}
            self._browser = await self._pw.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(**context_kwargs)

            seed = dict(self.cookies) if self.cookies else {}
            seed.setdefault("safe", "1")
            await self._set_context_cookies(seed)

            page = await self._context.new_page()

            async def _route(route: Any) -> None:
                req = route.request
                url = (req.url or "").lower()
                if req.resource_type in {"image", "media", "font"}:
                    await route.abort()
                    return
                if req.resource_type == "script" and "static/safe/js/" not in url:
                    await route.continue_()
                    return
                await route.continue_()

            await page.route("**/*", _route)
            self._page = page
        except NotImplementedError as exc:
            await self._close_on_loop()
            raise RuntimeError(
                "浏览器引擎无法启动：当前事件循环不支持子进程。"
                "请确认后端已加载独立 Proactor 循环后重试。"
            ) from exc
        except Exception:
            await self._close_on_loop()
            raise

    async def _set_context_cookies(self, cookies: dict[str, str]) -> None:
        if not self._context:
            return
        payload = []
        for name, value in cookies.items():
            if not value:
                continue
            for domain in COOKIE_DOMAINS:
                payload.append(
                    {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": "/",
                    }
                )
        if payload:
            try:
                await self._context.add_cookies(payload)
            except Exception as exc:
                log.debug("add_cookies failed: %s", exc)
        self.update(cookies)

    async def _sync_cookies_from_context(self) -> None:
        if not self._context:
            return
        raw = await self._context.cookies()
        self.cookies = {c["name"]: c["value"] for c in raw}
        self.cookies.setdefault("safe", "1")
        self.save()

    @staticmethod
    async def _click_age_gate(page: Page) -> bool:
        selectors = [
            "a.enter-btn",
            "text=满18岁",
            "text=If you are over 18",
            ".btn-enter",
            "text=请点此进入",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=1500):
                    await el.click(timeout=4000)
                    return True
            except Exception:
                continue
        try:
            return bool(
                await page.evaluate(
                    """() => {
                        const btn = document.querySelector('a.enter-btn');
                        if (btn) { btn.click(); return true; }
                        return false;
                    }"""
                )
            )
        except Exception:
            return False

    @staticmethod
    def is_safe_shell(html: str) -> bool:
        if not html:
            return True
        lowered = html.lower()
        return len(html) < 12000 and ("var safeid" in html or "static/safe/" in lowered)

    @staticmethod
    def _looks_like_age_gate(title: str, html: str) -> bool:
        blob = f"{title}\n{html[:4000]}".lower()
        markers = ("满18岁", "over 18", "please click here", "请点此进入", "a.enter-btn", "enter-btn")
        return any(m in blob or m in html for m in markers)

    @staticmethod
    def _extract_safeid(html: str) -> str:
        import re

        m = re.search(r"safeid\s*=\s*['\"]([^'\"]+)['\"]", html or "")
        return m.group(1) if m else ""
