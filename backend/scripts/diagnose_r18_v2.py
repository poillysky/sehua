"""Compare HTTP vs browser for list/thread; try browser-backed fetch fallback."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from playwright.async_api import async_playwright

from crawler.session import BASE_URL, DEFAULT_UA

URLS = [
    f"{BASE_URL}forum-2-1.html",
    f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats",
    f"{BASE_URL}forum.php",
]


def brief(html: str) -> str:
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.I | re.S)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:60] if title_m else ""
    ok = "Discuz" in (html or "") and "var safeid" not in (html or "")
    return f"len={len(html or '')} ok={ok} title={title!r}"


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=DEFAULT_UA, locale="zh-CN")
        # preseed safe=1 like ed2k
        await context.add_cookies(
            [
                {"name": "safe", "value": "1", "domain": ".sehuatang.net", "path": "/"},
                {"name": "safe", "value": "1", "domain": "www.sehuatang.net", "path": "/"},
            ]
        )
        page = await context.new_page()
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        for sel in ["a.enter-btn", "text=满18岁", "text=If you are over 18"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=1500):
                    await el.click()
                    print("clicked", sel)
                    await page.wait_for_timeout(3000)
                    break
            except Exception:
                pass

        for url in URLS:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2500)
            html = await page.content()
            print("browser", url.split("/")[-1][:50], brief(html))

        cookies = {c["name"]: c["value"] for c in await context.cookies()}
        print("cookies", sorted(cookies.keys()))

        # extract a thread url from last list
        await page.goto(f"{BASE_URL}forum-2-1.html", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        tids = re.findall(r"thread-(\d+)-1-1\.html", html)
        thread_url = f"{BASE_URL}thread-{tids[0]}-1-1.html" if tids else ""
        print("sample tid", tids[:3])

        headers = {
            "User-Agent": DEFAULT_UA,
            "Referer": f"{BASE_URL}forum.php",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            for url in URLS + ([thread_url] if thread_url else []):
                # attempt 1
                r = await client.get(url, cookies=cookies, headers=headers)
                html = r.text
                print("http1", url.split("/")[-1][:50], brief(html))
                if "var safeid" in html:
                    m = re.search(r"safeid\s*=\s*['\"]([^'\"]+)['\"]", html)
                    if m:
                        cookies["_safe"] = m.group(1)
                        cookies["safe"] = "1"
                        r = await client.get(url, cookies=cookies, headers=headers)
                        print("http2+safeid", url.split("/")[-1][:50], brief(r.text))

        # browser fetch fallback same page via page.request (uses browser cookie jar + fingerprint)
        api = context.request
        for url in URLS:
            resp = await api.get(url)
            text = await resp.text()
            print("pw-request", url.split("/")[-1][:50], brief(text))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
