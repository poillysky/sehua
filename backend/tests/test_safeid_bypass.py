"""Demonstrate R18 quote page auto-bypass via safeid cookie."""
import asyncio
import re
import httpx
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
SAFEID_RE = re.compile(r"safeid\s*=\s*['\"]([^'\"]+)['\"]")


def is_r18_block(html: str) -> bool:
    return bool(html) and len(html) < 10000 and "var safeid" in html


def is_real_thread(html: str) -> bool:
    return "Powered by Discuz" in html and "postmessage" in html


async def get_thread_url() -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="zh-CN")
        page = await ctx.new_page()
        await page.goto("https://www.sehuatang.net/", timeout=30000)
        await page.wait_for_timeout(2000)
        for sel in ["text=满18岁", "text=If you are over 18"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(4000)
        await page.goto("https://www.sehuatang.net/forum-103-1.html", timeout=30000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        tids = re.findall(r"thread-(\d+)-1-1\.html", html)
        await browser.close()
        return f"https://www.sehuatang.net/thread-{tids[0]}-1-1.html"


async def fetch_with_r18_bypass(url: str, cookies: dict) -> tuple[str, int, str]:
    headers = {"User-Agent": UA, "Referer": "https://www.sehuatang.net/forum-103-1.html"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        r = await client.get(url, cookies=cookies, headers=headers)
        html = r.text
        if is_r18_block(html):
            m = SAFEID_RE.search(html)
            if m:
                cookies["_safe"] = m.group(1)
                title = re.search(r"<title>(.*?)</title>", html, re.I)
                print(f"  [R18] 命中名言拦截页 title={title.group(1) if title else '?'} safeid={m.group(1)}")
                print(f"  [R18] 写入 _safe cookie，重试...")
                r = await client.get(url, cookies=cookies, headers=headers)
                html = r.text
        title = re.search(r"<title>(.*?)</title>", html, re.I)
        return html, len(html), title.group(1) if title else ""


async def main():
    thread_url = await get_thread_url()
    print(f"Target: {thread_url}\n")

    # Simulate: no _safe cookie (will hit quote page)
    cookies = {}
    html, length, title = await fetch_with_r18_bypass(thread_url, cookies)
    print(f"Result: len={length} real_thread={is_real_thread(html)} title={title[:40]}")

    # Simulate multiple reads with only safeid refresh (no browser)
    print("\n--- Simulate 5 thread reads, starting with empty cookies ---")
    cookies = {}
    for i in range(5):
        # rotate through different threads
        tid = re.search(r"thread-(\d+)", thread_url).group(1)
        url = f"https://www.sehuatang.net/thread-{int(tid)+i}-1-1.html"
        html, length, title = await fetch_with_r18_bypass(url, cookies)
        status = "OK" if is_real_thread(html) else ("R18" if is_r18_block(html) else "FAIL")
        print(f"  read#{i+1} [{status}] len={length} _safe={cookies.get('_safe','')[:12]}...")


if __name__ == "__main__":
    asyncio.run(main())
