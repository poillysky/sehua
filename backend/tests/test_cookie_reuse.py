import asyncio
import re
import httpx
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def bootstrap():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="zh-CN")
        page = await ctx.new_page()
        await page.goto("https://www.sehuatang.net/", timeout=30000)
        await page.wait_for_timeout(3000)
        for sel in ["text=满18岁", "text=If you are over 18"]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.click()
                    break
            except Exception:
                pass
        await page.wait_for_timeout(5000)
        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
        await browser.close()
        return cookies


async def main():
    cookies = await bootstrap()
    urls = [
        "https://www.sehuatang.net/forum.php",
        "https://www.sehuatang.net/forum-2-1.html",
    ]
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": UA, "Referer": "https://www.sehuatang.net/"},
    ) as client:
        for url in urls:
            r = await client.get(url, cookies=cookies)
            html = r.text
            tids = re.findall(r"thread-(\d+)-", html)
            is_discuz = "discuz" in html.lower()
            is_gate = "safe/js" in html
            print(f"URL: {url}")
            print(f"  status={r.status_code} len={len(html)} discuz={is_discuz} gate={is_gate}")
            print(f"  thread ids: {len(set(tids))} sample={list(set(tids))[:5]}")


if __name__ == "__main__":
    asyncio.run(main())
