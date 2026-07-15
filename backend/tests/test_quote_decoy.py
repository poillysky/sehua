"""Reproduce quote/decoy pages on thread reads."""
import asyncio
import random
import re
import httpx
from playwright.async_api import async_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

QUOTE_AUTHORS = [
    "尼采", "亚里士多德", "康德", "柏拉图", "黑格尔", "卢梭", "伏尔泰",
    "笛卡尔", "斯宾诺莎", "休谟", "叔本华", "罗素", "马克思", "恩格斯",
]


def classify(html: str) -> str:
    title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    title = (title_m.group(1) if title_m else "").strip()
    if any(a in title for a in QUOTE_AUTHORS):
        return "QUOTE_DECOY"
    if "Powered by Discuz" in html and ("postmessage" in html or 'id="post_' in html):
        return "REAL_THREAD"
    if "safe/js" in html or "safeid" in html:
        return "SAFE_GATE"
    if "challenge-platform" in html:
        return "CF_CHALLENGE"
    if "404" in title:
        return "404"
    if len(html) < 6000 and "SEHUATANG" in html.upper():
        return "QUOTE_DECOY"
    return "UNKNOWN"


async def bootstrap_cookies() -> dict:
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


async def collect_thread_urls(cookies: dict, fid: int = 103) -> list[str]:
    list_url = f"https://www.sehuatang.net/forum-{fid}-1.html"
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        r = await client.get(
            list_url,
            cookies=cookies,
            headers={"User-Agent": UA, "Referer": "https://www.sehuatang.net/forum.php"},
        )
        html = r.text
    # correct format: thread-{tid}-1-1.html
    tids = list(dict.fromkeys(re.findall(r"thread-(\d+)-1-1\.html", html)))
    return [f"https://www.sehuatang.net/thread-{tid}-1-1.html" for tid in tids[:10]]


def show_result(label: str, html: str, url: str):
    kind = classify(html)
    title_m = re.search(r"<title>(.*?)</title>", html, re.I)
    title = title_m.group(1) if title_m else ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())[:180]
    print(f"{label:28} | {kind:12} | len={len(html):6} | {title[:25]}")
    if kind != "REAL_THREAD":
        print(f"{'':28}   preview: {text}")


async def test_wrong_url_format(cookies: dict, tid: str):
    print("\n=== Wrong vs correct URL format ===")
    wrong = f"https://www.sehuatang.net/thread-{tid}-1.html"
    right = f"https://www.sehuatang.net/thread-{tid}-1-1.html"
    headers = {"User-Agent": UA, "Referer": "https://www.sehuatang.net/forum-103-1.html"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        for label, url in [("WRONG -1.html", wrong), ("CORRECT -1-1.html", right)]:
            r = await client.get(url, cookies=cookies, headers=headers)
            show_result(label, r.text, url)


async def test_httpx_reads(cookies: dict, urls: list[str]):
    print("\n=== httpx read threads (with referer, 2s delay) ===")
    headers_base = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    stats = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        for i, url in enumerate(urls):
            headers = {**headers_base, "Referer": "https://www.sehuatang.net/forum-103-1.html"}
            r = await client.get(url, cookies=cookies, headers=headers)
            kind = classify(r.text)
            stats[kind] = stats.get(kind, 0) + 1
            show_result(f"httpx #{i+1}", r.text, url)
            await asyncio.sleep(2)


async def test_httpx_no_referer(cookies: dict, url: str):
    print("\n=== httpx WITHOUT referer ===")
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        r = await client.get(url, cookies=cookies, headers={"User-Agent": UA})
        show_result("no referer", r.text, url)


async def test_httpx_rapid(cookies: dict, urls: list[str]):
    print("\n=== httpx rapid burst (no delay) ===")
    headers = {"User-Agent": UA, "Referer": "https://www.sehuatang.net/forum-103-1.html"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as client:
        for i, url in enumerate(urls[:6]):
            r = await client.get(url, cookies=cookies, headers=headers)
            show_result(f"burst #{i+1}", r.text, url)


async def test_playwright_reads(urls: list[str]):
    print("\n=== Playwright navigate threads (natural) ===")
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

        # natural flow: list -> thread
        await page.goto("https://www.sehuatang.net/forum-103-1.html", timeout=30000)
        await page.wait_for_timeout(2000)
        for i in range(min(5, len(urls))):
            tid = re.search(r"thread-(\d+)", urls[i]).group(1)
            link = page.locator(f'a[href*="thread-{tid}-1-1.html"]').first
            await link.click()
            await page.wait_for_timeout(random.uniform(2, 4))
            html = await page.content()
            show_result(f"click thread #{i+1}", html, page.url)

        # direct goto (unnatural)
        print("\n=== Playwright direct goto threads ===")
        for i, url in enumerate(urls[:4]):
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(1500)
            html = await page.content()
            show_result(f"direct #{i+1}", html, page.url)

        await browser.close()


async def main():
    cookies = await bootstrap_cookies()
    urls = await collect_thread_urls(cookies, fid=103)
    print(f"Collected {len(urls)} thread URLs")
    if not urls:
        return

    tid = re.search(r"thread-(\d+)", urls[0]).group(1)
    await test_wrong_url_format(cookies, tid)
    await test_httpx_reads(cookies, urls[:6])
    await test_httpx_no_referer(cookies, urls[0])
    await test_httpx_rapid(cookies, urls)
    await test_playwright_reads(urls)


if __name__ == "__main__":
    asyncio.run(main())
