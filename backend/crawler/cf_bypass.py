"""Cloudflare challenge detection + Playwright wait / FlareSolverr helpers."""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

CF_STATUS = {403, 429, 503}
CF_KEYWORDS = (
    "just a moment",
    "attention required",
    "challenge-platform",
    "cf-browser-verification",
    "cf-challenge",
    "cf-turnstile",
    "turnstile",
    "checking your browser",
    "enable javascript and cookies",
    "cdn-cgi/challenge",
    "window._cf_chl_opt",
    "__cf_chl_tk",
    "为什么要完成验证",  # 部分中文 CF 页
    "正在验证",
    "正在进行安全验证",
    "请完成以下操作",
    "verify you are human",
)
# 交互式 Turnstile：无头 Chromium 几乎过不了，应尽快交给 FlareSolverr
INTERACTIVE_CF_MARKERS = (
    "请稍候",
    "稍候",
    "正在进行安全验证",
    "正在验证",
    "cf-turnstile",
    "challenges.cloudflare.com",
    "verify you are human",
    "请完成以下操作",
    "为什么要完成验证",
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

_FLARE_CANDIDATES = (
    "http://127.0.0.1:8191/v1",
    "http://127.0.0.1:8191",
    "http://127.0.0.1:8192/v1",
)
_flare_discovered: Optional[str] = None
_flare_probe_at: float = 0.0


def extract_title(html: str) -> str:
    m = TITLE_RE.search(html or "")
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def is_interactive_cf(html: str) -> bool:
    """是否像需要人工/专用浏览器过的 Turnstile 交互页。"""
    raw = html or ""
    if not is_cf_challenge(raw):
        return False
    blob = f"{extract_title(raw)}\n{raw[:14000]}".lower()
    return any(m.lower() in blob for m in INTERACTIVE_CF_MARKERS)


def is_cf_challenge(html: str, status: int = 200) -> bool:
    """是否仍停在 Cloudflare 挑战页（已过关的论坛长页不算）。"""
    raw = html or ""
    lower = raw[:12000].lower()
    title = extract_title(raw).lower()
    cf_title = any(
        t in title
        for t in (
            "just a moment",
            "attention required",
            "请稍候",
            "稍候",
            "正在验证",
        )
    )
    # 已进入真实论坛页：即使脚本残留 challenge 字样也不算卡在 CF
    forum_ok = any(
        k in lower
        for k in (
            "powered by discuz",
            "powered by phpwind",
            "postmessage_",
            'id="read_tpc"',
            "id='read_tpc'",
            "forumdisplay",
            "threadlist",
        )
    ) or len(raw) > 40000
    if forum_ok and not cf_title:
        return False

    if any(k in lower or k in title for k in CF_KEYWORDS) or cf_title:
        return True

    if status in CF_STATUS:
        if status == 503 and len(raw) > 12000 and forum_ok:
            return False
        if status in {403, 429} and len(raw) < 8000 and not forum_ok:
            return True
    return False


def resolve_flaresolverr_url(explicit: str | None = None) -> Optional[str]:
    """环境变量优先；遇 CF 时可自动探测本机 FlareSolverr（默认开）。"""
    global _flare_discovered, _flare_probe_at
    raw = (explicit or os.environ.get("SHT_FLARESOLVERR_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    autodisc = (os.environ.get("SHT_FLARESOLVERR_AUTODISCOVER") or "1").strip().lower()
    if autodisc in {"0", "false", "no", "off"}:
        return None
    # 缓存探测结果，避免每次扫端口；失败也冷却 30s
    now = time.monotonic()
    if _flare_discovered:
        return _flare_discovered
    if now - _flare_probe_at < 30:
        return None
    _flare_probe_at = now
    found = _probe_flaresolverr()
    if found:
        _flare_discovered = found
    return found


def _probe_flaresolverr() -> Optional[str]:
    try:
        from curl_cffi import requests as crequests
    except ImportError:
        return None
    for base in _FLARE_CANDIDATES:
        try:
            r = crequests.get(base if base.endswith("/v1") else base, timeout=1.5)
            # FlareSolverr GET / 常 405/200；通了就算
            if r.status_code < 500:
                url = base if base.endswith("/v1") else f"{base.rstrip('/')}/v1"
                log.info("Auto-discovered FlareSolverr at %s", url)
                return url
        except Exception:
            continue
    return None


def cf_browser_wait_ms(html: str = "") -> int:
    """交互式 CF 缩短本机等待，尽快交给 FlareSolverr。"""
    default = int(os.getenv("SHT_CF_WAIT_MS", "45000") or "45000")
    if html and is_interactive_cf(html):
        short = int(os.getenv("SHT_CF_INTERACTIVE_WAIT_MS", "12000") or "12000")
        return max(5000, min(default, short))
    return max(8000, default)


async def wait_out_cf_challenge(
    page: Any,
    *,
    timeout_ms: int = 45000,
    poll_ms: int = 1500,
) -> str:
    """在已打开的页面上等待 CF 挑战结束（含尝试点 Turnstile）。"""
    deadline = time.monotonic() + max(5.0, timeout_ms / 1000.0)
    tried_click = False
    clearance_reloads = 0
    while True:
        html = ""
        title = ""
        try:
            html = await page.content()
            title = await page.title()
        except Exception:
            pass
        blob = f"{title}\n{(html or '')[:10000]}"
        if not is_cf_challenge(blob):
            return html or ""

        # cf_clearance 出现通常表示过关中/已过（最多刷新 2 次，避免死循环）
        try:
            cookies = await page.context.cookies()
            has_clearance = any(
                c.get("name") == "cf_clearance" and c.get("value") for c in cookies
            )
            if has_clearance and clearance_reloads < 2:
                clearance_reloads += 1
                await page.wait_for_timeout(min(2500, poll_ms * 2))
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
                html2 = await page.content()
                title2 = ""
                try:
                    title2 = await page.title()
                except Exception:
                    pass
                if not is_cf_challenge(f"{title2}\n{html2}"):
                    return html2
                html = html2
        except Exception:
            pass

        if not tried_click:
            tried_click = True
            await _try_click_turnstile(page)

        if time.monotonic() >= deadline:
            return html or ""
        await page.wait_for_timeout(poll_ms)


async def _try_click_turnstile(page: Any) -> None:
    """尽力点击 Turnstile / CF 复选框（失败忽略）。"""
    selectors = (
        'iframe[src*="challenges.cloudflare.com"]',
        'iframe[src*="turnstile"]',
        "#challenge-stage iframe",
        ".cf-turnstile iframe",
    )
    for sel in selectors:
        try:
            loc = page.frame_locator(sel).first
            # 点 iframe 内 body / checkbox
            box = loc.locator("input[type=checkbox], body")
            await box.first.click(timeout=2500, force=True)
            log.info("Clicked Cloudflare turnstile frame (%s)", sel)
            await page.wait_for_timeout(2000)
            return
        except Exception:
            continue
    try:
        await page.locator("#challenge-stage, .cf-turnstile, text=Verify").first.click(
            timeout=2000
        )
        await page.wait_for_timeout(1500)
    except Exception:
        pass


def flaresolverr_get(
    api_url: str,
    url: str,
    *,
    cookies: dict[str, str] | None = None,
    proxy: str = "",
    timeout: float = 120.0,
    max_timeout_ms: int = 90000,
) -> Optional[dict[str, Any]]:
    """调用 FlareSolverr，成功返回 solution dict。"""
    try:
        from curl_cffi import requests as crequests
    except ImportError:
        return None
    endpoint = api_url if api_url.rstrip("/").endswith("/v1") else f"{api_url.rstrip('/')}/v1"
    # 过期/失效的 cf_clearance 会拖住挑战；交给 FlareSolverr 时先丢掉
    cookie_items = dict(cookies or {})
    cookie_items.pop("cf_clearance", None)
    payload: dict[str, Any] = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": max(30000, int(max_timeout_ms)),
    }
    if cookie_items:
        payload["cookies"] = [
            {"name": k, "value": v} for k, v in cookie_items.items() if v
        ]
    if proxy:
        # FlareSolverr 期望 http://host:port
        payload["proxy"] = {"url": proxy}
    try:
        r = crequests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        data = r.json() or {}
        solution = data.get("solution") or {}
        if data.get("status") != "ok" and solution.get("status") not in (200, "200"):
            # 兼容旧版：只看 solution.status
            if int(solution.get("status") or 0) != 200:
                log.error(
                    "FlareSolverr failed status=%s message=%s sol=%s",
                    data.get("status"),
                    data.get("message"),
                    solution.get("status"),
                )
                return None
        return solution
    except Exception as e:
        log.error("FlareSolverr error: %s", e)
        return None


def site_root_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}/"
    except Exception:
        pass
    return ""
