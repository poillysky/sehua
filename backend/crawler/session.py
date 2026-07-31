"""Browser session for age gate + list pages; cookie jar for HTTP thread reads."""

from __future__ import annotations

import json
import logging
import os
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

# 长跑时 Chromium 堆/缓存会胀到 GB；每 N 次浏览器操作软回收一次（0=关闭）
def _recycle_every() -> int:
    try:
        return max(0, int(os.getenv("PW_RECYCLE_EVERY", "60") or "60"))
    except (TypeError, ValueError):
        return 60


_CHROMIUM_LAUNCH_ARGS = (
    "--disable-dev-shm-usage",
    "--disk-cache-size=1",
    "--media-cache-size=1",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
)


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
        cookie_domains: tuple[str, ...] | list[str] | None = None,
    ):
        self.user_agent = user_agent or DEFAULT_UA
        self.cookie_file = cookie_file
        self.proxy = (proxy or "").strip()
        self.cookie_domains: tuple[str, ...] = tuple(
            d for d in (cookie_domains or COOKIE_DOMAINS) if d
        ) or COOKIE_DOMAINS
        self.cookies: dict[str, str] = {}
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._ready = False
        self.active_entry_url: str = BASE_URL
        self._browser_ops = 0
        self._recycle_every = _recycle_every()

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
        """落盘 Cookie；短时节流，避免每帖连写三次拖 IO。"""
        import time

        now = time.monotonic()
        last = float(getattr(self, "_last_save_mono", 0) or 0)
        if now - last < 8.0 and self.cookie_file.is_file():
            self._save_pending = True
            return
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies.setdefault("safe", "1")
        self.cookie_file.write_text(
            json.dumps(self.cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._last_save_mono = now
        self._save_pending = False
        log.info("Saved cookies to %s", self.cookie_file)

    def flush_save(self) -> None:
        """强制落盘（会话关闭时调用）。"""
        self._last_save_mono = 0.0
        self.save()

    def update(self, cookies: dict[str, str]) -> None:
        for key, value in cookies.items():
            if value:
                self.cookies[key] = value
        self.cookies.setdefault("safe", "1")

    def apply_config_cookie_authority(self) -> None:
        """进站前应用配置 Cookie 权威性。

        - 已注入登录键：与 jar 合并（注入覆盖）
        - 仅游客：不 load jar，避免磁盘旧登录态复活
        """
        injected = dict(self.cookies)
        injected_auth = {k: v for k, v in injected.items() if k != "safe" and v}
        if injected_auth:
            self.load()
            self.cookies.update({k: v for k, v in injected.items() if v})
            self.cookies.setdefault("safe", "1")
        else:
            self.cookies = {"safe": str(injected.get("safe") or "1")}

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
        # force 重进站时优先沿用本会话已成功入口，避免误回色花堂默认域
        active = (self.active_entry_url or "").strip()
        if active and active not in candidates:
            candidates.append(active)
        if not candidates:
            candidates = [BASE_URL]

        # 配置 Cookie 权威（游客不复活 jar 登录态）
        injected = dict(self.cookies)
        self.apply_config_cookie_authority()
        last_err: Exception | None = None
        from crawler.list_urls import site_root

        for home in candidates:
            try:
                await self._close_on_loop()
                await self._ensure_browser()
                assert self._page
                page = self._page
                await page.goto(home, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1200)
                if await self._click_age_gate(page):
                    log.info("Age gate clicked (%s)", home)
                    await page.wait_for_timeout(3000)

                # 跳转后以实际落地页为站点根（发布页 /lt1.php → 当日 BBS）
                landed = ""
                try:
                    landed = (page.url or "").strip()
                except Exception:
                    landed = ""
                root = site_root(landed or home)
                from urllib.parse import urlparse

                def _host(u: str) -> str:
                    try:
                        return (urlparse(u).netloc or "").lower()
                    except Exception:
                        return ""

                probe = ""
                if probe_url and _host(probe_url) and _host(probe_url) == _host(root):
                    probe = probe_url.strip()
                elif "thread.php" in (home or "").lower() or any(
                    x in root.lower()
                    for x in ("xc6ym5", "2048", "hjd2048", "a22e7", "bbs.", ":2048", ":5680")
                ):
                    probe = f"{root}thread.php?fid=2"
                elif probe_url and "thread.php" in probe_url.lower():
                    # 调用方指定 PHPWind 探测，但入口已换域 → 按当前根重建
                    probe = f"{root}thread.php?fid=2"
                else:
                    probe = f"{root}forum-2-1.html"
                # 按实际入口刷新 cookie 域名（镜像 failover）
                derived = []
                try:
                    from crawler.sites.base import domains_from_entry

                    derived = list(domains_from_entry(landed or home))
                except Exception:
                    derived = []
                if derived:
                    merged = list(dict.fromkeys([*self.cookie_domains, *derived]))
                    self.cookie_domains = tuple(merged)
                    # 镜像换域后把登录 Cookie 种到新域名，否则 winduser 只挂在旧域
                    await self._set_context_cookies(dict(self.cookies))
                html = await self._fetch_html_on_loop(probe)
                if self.is_safe_shell(html):
                    raise RuntimeError(f"仍卡在十八禁/安全浏览壳，无法进入论坛：{home}")

                await self._sync_cookies_from_context()
                # sync 只反映浏览器当前域；补回注入的登录键（若站点未回写）
                for key, value in injected.items():
                    if value and key not in self.cookies:
                        self.cookies[key] = value
                self.cookies.setdefault("safe", "1")
                self._ready = True
                self.active_entry_url = root
                log.info(
                    "Browser session ready via %s (from %s) cookies=%s",
                    root,
                    home,
                    ",".join(sorted(self.cookies.keys())),
                )
                return self.cookies
            except Exception as exc:
                last_err = exc
                log.warning("Entry failover: %s failed: %s", home, _fmt_exc(exc))
                try:
                    from workers.runner import _log_activity

                    _log_activity(f"进站失败 · {_fmt_exc(exc)[:80]} · 换下一条")
                except Exception:
                    pass
                continue

        await self._close_on_loop()
        raise RuntimeError(f"论坛进站失败：所有入口均未能完成浏览器初始化（{_fmt_exc(last_err)}）")

    async def fetch_html(self, url: str, *, timeout_ms: int = 60000) -> str:
        """浏览器导航取 HTML（列表页主路径）。"""
        return await run_on_pw_loop(self._fetch_html_on_loop(url, timeout_ms=timeout_ms))

    async def _fetch_html_on_loop(self, url: str, *, timeout_ms: int = 60000) -> str:
        await self._maybe_recycle_on_loop()
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

        # Cloudflare：被动 JS 挑战可等；交互 Turnstile 缩短等待，交给上层 FlareSolverr
        try:
            from crawler.cf_bypass import (
                cf_browser_wait_ms,
                is_cf_challenge,
                is_interactive_cf,
                wait_out_cf_challenge,
            )

            blob0 = f"{title}\n{html}"
            if is_cf_challenge(blob0):
                interactive = is_interactive_cf(blob0)
                cf_wait = cf_browser_wait_ms(blob0)
                log.info(
                    "Cloudflare challenge on %s · waiting browser solve… "
                    "(interactive=%s wait_ms=%s)",
                    url,
                    interactive,
                    cf_wait,
                )
                html = await wait_out_cf_challenge(page, timeout_ms=cf_wait)
                try:
                    title = await page.title()
                except Exception:
                    title = ""
                if is_cf_challenge(f"{title}\n{html}"):
                    log.warning(
                        "Cloudflare still present after wait: %s "
                        "(will try FlareSolverr if available)",
                        url,
                    )
        except Exception as cf_exc:
            log.debug("CF wait skipped: %s", cf_exc)

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

    async def rebind_browser_identity(
        self,
        *,
        user_agent: str = "",
        cookies: dict[str, str] | None = None,
    ) -> None:
        """FlareSolverr 过关后：用其 UA + cf_clearance 重建浏览器上下文。

        clearance 绑定求解时的 UA；只 add_cookies 不换 UA 时，附件页仍会被 CF 打回。
        """
        await run_on_pw_loop(
            self._rebind_browser_identity_on_loop(
                user_agent=user_agent, cookies=cookies
            )
        )

    async def _rebind_browser_identity_on_loop(
        self,
        *,
        user_agent: str = "",
        cookies: dict[str, str] | None = None,
    ) -> None:
        ua = (user_agent or self.user_agent or DEFAULT_UA).strip() or DEFAULT_UA
        if ua != self.user_agent:
            log.info("Rebind browser UA after CF solve: %s…", ua[:72])
            self.user_agent = ua
        jar = dict(cookies) if cookies is not None else dict(self.cookies)
        jar.setdefault("safe", "1")
        self.update(jar)

        await self._ensure_browser()
        assert self._browser is not None

        # 关掉旧 context/page，保留 browser 进程
        for obj in (self._page, self._context):
            if obj is None:
                continue
            try:
                await obj.close()
            except Exception:
                pass
        self._page = None
        self._context = None

        context_kwargs: dict[str, Any] = {
            "user_agent": self.user_agent,
            "locale": "zh-CN",
            "viewport": {"width": 1366, "height": 768},
        }
        if self.proxy:
            context_kwargs["proxy"] = {"server": self.proxy}
        self._context = await self._browser.new_context(**context_kwargs)
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        # 此处必须注入 cf_clearance（与 FlareSolverr UA 成对）
        await self._set_context_cookies(jar)

        page = await self._context.new_page()

        async def _route(route: Any) -> None:
            req = route.request
            url = (req.url or "").lower()
            if any(
                k in url
                for k in (
                    "cloudflare",
                    "turnstile",
                    "cdn-cgi",
                    "cf-challenge",
                    "challenge-platform",
                )
            ):
                await route.continue_()
                return
            if req.resource_type in {"image", "media", "font"}:
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", _route)
        self._page = page
        self._ready = True
        log.info(
            "Browser identity rebound · ua=%s… · cookies=%d · has_cf=%s",
            (self.user_agent or "")[:48],
            len(jar),
            bool(jar.get("cf_clearance")),
        )

    async def close(self) -> None:
        await run_on_pw_loop(self._close_on_loop())

    async def _close_on_loop(self) -> None:
        try:
            if getattr(self, "_save_pending", False):
                self.flush_save()
        except Exception:
            log.debug("flush cookies on close failed", exc_info=True)
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

    async def run_on_page(self, fn: Any, *, timeout: float | None = None) -> Any:
        """在浏览器循环上执行依赖当前 page 的协程工厂 `async def fn(page)`。

        timeout：覆盖默认 PW_OP_TIMEOUT（附件下载应传更短，避免多附件串行卡死）。
        """

        async def _body() -> Any:
            await self._maybe_recycle_on_loop()
            await self._ensure_browser()
            assert self._page
            return await fn(self._page)

        return await run_on_pw_loop(_body(), timeout=timeout)

    async def _close_extra_pages_on_loop(self) -> None:
        """关掉附件弹窗等非主 page，避免同 context 页面积压占内存。"""
        if not self._context or not self._page:
            return
        for p in list(self._context.pages):
            if p is self._page:
                continue
            try:
                await p.close()
            except Exception:
                pass

    async def _maybe_recycle_on_loop(self) -> None:
        """长跑周期性软回收 Chromium，把 RSS 从 GB 级拉回基线附近。"""
        await self._close_extra_pages_on_loop()
        every = int(self._recycle_every or 0)
        if every <= 0 or not self._ready:
            return
        self._browser_ops += 1
        if self._browser_ops < every:
            return
        self._browser_ops = 0
        log.info("Recycling Playwright browser after %s ops (RSS control)", every)
        try:
            await self._sync_cookies_from_context()
        except Exception:
            pass
        home = (self.active_entry_url or BASE_URL).strip() or BASE_URL
        await self._close_on_loop()
        try:
            await self._ensure_browser()
            assert self._page
            page = self._page
            await page.goto(home, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(1500)
            if await self._click_age_gate(page):
                await page.wait_for_timeout(2000)
            await self._sync_cookies_from_context()
            self._ready = True
            log.info("Browser recycled via %s", home)
        except Exception as exc:
            log.warning(
                "Browser recycle soft-enter failed: %s — next fetch will rebootstrap",
                _fmt_exc(exc),
            )
            self._ready = False
            await self._close_on_loop()

    async def _ensure_browser(self) -> None:
        if self._page and self._context and self._browser:
            return

        log.info(
            "Launching Playwright chromium for crawl%s...",
            f" proxy={self.proxy}" if self.proxy else "",
        )
        try:
            self._pw = await async_playwright().start()
            # 新 headless 指纹更接近真机；可用 SHT_PW_CHANNEL=chrome|msedge 指定系统浏览器
            headless_mode: Any = True
            if (os.getenv("SHT_PW_HEADLESS_SHELL") or "").strip().lower() in {
                "0",
                "false",
                "no",
                "off",
            }:
                headless_mode = False
            elif (os.getenv("SHT_PW_HEADLESS_NEW") or "1").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }:
                headless_mode = True
            launch_kwargs: dict[str, Any] = {
                "headless": headless_mode,
                "args": list(_CHROMIUM_LAUNCH_ARGS),
            }
            channel = (os.getenv("SHT_PW_CHANNEL") or "").strip().lower()
            if channel in {"chrome", "msedge", "chromium", "chrome-beta"}:
                launch_kwargs["channel"] = channel
            context_kwargs: dict[str, Any] = {
                "user_agent": self.user_agent,
                "locale": "zh-CN",
                "viewport": {"width": 1366, "height": 768},
            }
            if self.proxy:
                context_kwargs["proxy"] = {"server": self.proxy}
            self._browser = await self._pw.chromium.launch(**launch_kwargs)
            self._context = await self._browser.new_context(**context_kwargs)
            # 弱化 webdriver 特征（对部分被动 CF 有帮助）
            await self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            seed = dict(self.cookies) if self.cookies else {}
            seed.setdefault("safe", "1")
            # 失效 cf_clearance 会反复卡在挑战页；启动时若强制重建可清掉
            if (os.getenv("SHT_CF_DROP_STALE_CLEARANCE") or "1").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }:
                # 保留 jar，但浏览器上下文先不注入旧 clearance，让挑战重发新 cookie
                seed.pop("cf_clearance", None)
            await self._set_context_cookies(seed)

            page = await self._context.new_page()

            async def _route(route: Any) -> None:
                req = route.request
                url = (req.url or "").lower()
                # Cloudflare / Turnstile 资源一律放行，否则过不了挑战
                if any(
                    k in url
                    for k in (
                        "cloudflare",
                        "turnstile",
                        "cdn-cgi",
                        "cf-challenge",
                        "challenge-platform",
                    )
                ):
                    await route.continue_()
                    return
                if req.resource_type in {"image", "media", "font"}:
                    await route.abort()
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
            for domain in self.cookie_domains:
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
        # 合并而非整表替换，避免换域/局部同步时丢掉已注入的登录 Cookie
        for c in raw:
            name = c.get("name") or ""
            value = c.get("value") or ""
            if name and value:
                self.cookies[name] = value
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
