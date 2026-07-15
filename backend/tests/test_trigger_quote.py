"""Try to trigger quote/decoy pages under various bad conditions."""
import asyncio
import re
import httpx
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
QUOTE_AUTHORS = ["尼采", "亚里士多德", "康德", "柏拉图", "黑格尔", "卢梭", "伏尔泰"]


def classify(html: str) -> tuple[str, str]:
    title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    title = (title_m.group(1) if title_m else "").strip()
    if any(a in title for a in QUOTE_AUTHORS):
        return "QUOTE_DECOY", title
    if "Powered by Discuz" in html and ("postmessage" in html or 'id="post_' in html):
        return "REAL_THREAD", title
    if "safe/js" in html or "safeid" in html:
        return "SAFE_GATE", title
    if "404" in title:
        return "404", title
    if len(html) < 6000:
        return "SMALL_PAGE", title
    return "OTHER", title


async def bootstrap() -> dict:
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
        await page.wait_for_timeout(5000)
        cookies = {c["name"]: c["value"] for c in await ctx.cookies()}
        await browser.close()
        return cookies


async def get_sample_thread(cookies: dict, fid: int) -> str | None:
    url = f"https://www.sehuatang.net/forum-{fid}-1.html"
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as c:
        r = await c.get(url, cookies=cookies, headers={"User-Agent": UA, "Referer": "https://www.sehuatang.net/"})
        tids = re.findall(r"thread-(\d+)-1-1\.html", r.text)
        if tids:
            return f"https://www.sehuatang.net/thread-{tids[0]}-1-1.html"
    return None


async def fetch(label: str, url: str, cookies: dict | None, referer: str | None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as c:
        r = await c.get(url, cookies=cookies or {}, headers=headers)
        kind, title = classify(r.text)
        print(f"{label:35} -> {kind:12} len={len(r.text):6} title={title[:30]}")
        if kind in ("QUOTE_DECOY", "SAFE_GATE", "SMALL_PAGE"):
            text = re.sub(r"<[^>]+>", " ", r.text)
            print(f"{'':35}    {(' '.join(text.split()))[:200]}")


async def main():
    cookies = await bootstrap()

    # test multiple forum sections including BT areas
    for fid in [103, 95, 36, 2, 75, 141]:
        thread = await get_sample_thread(cookies, fid)
        if not thread:
            print(f"fid={fid}: no thread found")
            continue
        await fetch(f"fid={fid} normal", thread, cookies, "https://www.sehuatang.net/forum.php")

    thread103 = await get_sample_thread(cookies, 103)
    if not thread103:
        return

    print("\n--- Trigger conditions ---")
    await fetch("no cookies", thread103, None, "https://www.sehuatang.net/forum-103-1.html")
    await fetch("no _safe cookie", thread103, {k: v for k, v in cookies.items() if k != "_safe"}, "https://www.sehuatang.net/")
    await fetch("no cf_clearance", thread103, {k: v for k, v in cookies.items() if k != "cf_clearance"}, "https://www.sehuatang.net/")
    await fetch("empty cookies", thread103, {}, "https://www.sehuatang.net/")
    await fetch("fake _safe", thread103, {**cookies, "_safe": "invalid123"}, "https://www.sehuatang.net/")

    # fresh browser session without age click - direct thread
    print("\n--- Playwright without age verify, direct thread ---")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, locale="zh-CN")
        page = await ctx.new_page()
        await page.goto(thread103, timeout=30000)
        await page.wait_for_timeout(3000)
        html = await page.content()
        kind, title = classify(html)
        print(f"{'pw no age verify':35} -> {kind:12} len={len(html):6} title={title[:30]}")
        if kind in ("QUOTE_DECOY", "SAFE_GATE", "SMALL_PAGE"):
            text = re.sub(r"<[^>]+>", " ", html)
            print(f"{'':35}    {(' '.join(text.split()))[:200]}")
        await browser.close()

    # simulate cookie expired: only discuz cookies no cf/safe
    discuz_only = {k: v for k, v in cookies.items() if k.startswith("cPNj")}
    await fetch("discuz cookies only", thread103, discuz_only, "https://www.sehuatang.net/")


if __name__ == "__main__":
    asyncio.run(main())
