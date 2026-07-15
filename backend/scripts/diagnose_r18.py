"""Diagnose why R18/safe shell persists on list pages."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from playwright.async_api import async_playwright

from crawler.session import BASE_URL, COOKIE_FILE, DEFAULT_UA, SessionManager

URL = f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats"
SAFEID_RE = re.compile(r"safeid\s*=\s*['\"]([^'\"]+)['\"]")


def summary(label: str, html: str, status: int = 0) -> None:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:80] if title_m else ""
    print(
        f"[{label}] status={status} len={len(html or '')} "
        f"safeid={'yes' if 'var safeid' in (html or '') else 'no'} "
        f"discuz={'yes' if 'Powered by Discuz' in (html or '') else 'no'} "
        f"title={title!r}"
    )


async def http_get(url: str, cookies: dict[str, str]) -> tuple[str, int]:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": f"{BASE_URL}forum.php",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url, cookies=cookies, headers=headers)
        return resp.text, resp.status_code


async def browser_probe() -> dict[str, str]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA, locale="zh-CN")
        page = await context.new_page()
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2500)
        clicked = False
        for sel in ["a.enter-btn", "text=满18岁", "text=If you are over 18", ".btn-enter"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=2000):
                    await el.click()
                    clicked = True
                    break
            except Exception:
                continue
        print(f"[browser] age-gate click={clicked}")
        await page.wait_for_timeout(4000)
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        html = await page.content()
        summary("browser-list", html)
        # if still shell, wait more / click again
        if "var safeid" in html and len(html) < 12000:
            # try set cookie safe=1 via JS eval path used by site
            m = SAFEID_RE.search(html)
            if m:
                await context.add_cookies(
                    [
                        {
                            "name": "_safe",
                            "value": m.group(1),
                            "domain": ".sehuatang.net",
                            "path": "/",
                        },
                        {
                            "name": "safe",
                            "value": "1",
                            "domain": ".sehuatang.net",
                            "path": "/",
                        },
                    ]
                )
                await page.reload(wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                html = await page.content()
                summary("browser-after-cookie", html)
        raw = await context.cookies()
        cookies = {c["name"]: c["value"] for c in raw}
        print("[browser] cookie keys:", sorted(cookies.keys()))
        await browser.close()
        return cookies


async def main() -> None:
    sm = SessionManager()
    loaded = sm.load()
    print(f"cookie file={COOKIE_FILE} loaded={loaded} keys={sorted(sm.cookies.keys())}")

    html, status = await http_get(URL, sm.cookies)
    summary("persist-cookies", html, status)

    cookies = dict(sm.cookies)
    cookies["safe"] = "1"
    html2, status2 = await http_get(URL, cookies)
    summary("persist+safe=1", html2, status2)

    if "var safeid" in html:
        m = SAFEID_RE.search(html)
        if m:
            cookies["_safe"] = m.group(1)
            html3, status3 = await http_get(URL, cookies)
            summary("persist+safeid", html3, status3)
            print("safeid sample:", m.group(1)[:40])
            print("html head:", html[:400].replace("\n", " "))

    fresh = await browser_probe()
    html4, status4 = await http_get(URL, fresh)
    summary("fresh-browser-cookies-http", html4, status4)
    fresh2 = dict(fresh)
    fresh2["safe"] = "1"
    html5, status5 = await http_get(URL, fresh2)
    summary("fresh+safe=1-http", html5, status5)


if __name__ == "__main__":
    asyncio.run(main())
