import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def bootstrap(page):
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


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="zh-CN")
        page = await ctx.new_page()
        await bootstrap(page)

        await page.goto("https://www.sehuatang.net/forum-103-1.html", timeout=30000)
        await page.wait_for_timeout(3000)
        html = await page.content()

        hrefs = re.findall(r'href="([^"]+)"', html)
        thread_hrefs = [h for h in hrefs if "thread" in h.lower()]
        print("thread href samples:")
        for h in thread_hrefs[:25]:
            print(" ", h)
        print("total:", len(thread_hrefs))

        # click first thread link naturally
        link = page.locator('a[href*="thread-"]').first
        href = await link.get_attribute("href")
        print("\nFirst thread link:", href)
        await link.click()
        await page.wait_for_timeout(3000)
        html2 = await page.content()
        title = re.search(r"<title>(.*?)</title>", html2, re.I)
        print("After click - url:", page.url)
        print("After click - len:", len(html2))
        print("After click - title:", title.group(1) if title else "")
        print("Has postmessage:", "postmessage" in html2)
        print("Is quote page:", any(x in (title.group(1) if title else "") for x in ["尼采", "康德", "亚里士多德"]))

        # save snippet for analysis
        out = ROOT / "fixtures" / "sample_thread.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html2[:8000], encoding="utf-8")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
