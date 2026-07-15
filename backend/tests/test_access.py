"""Compare HTTP vs browser access to sehuatang.net"""
import asyncio
import re
import httpx
from playwright.async_api import async_playwright


BASE = "https://www.sehuatang.net/"
FORUM_URL = "https://www.sehuatang.net/forum.php"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def analyze(label: str, html: str, url: str) -> dict:
    return {
        "label": label,
        "url": url,
        "length": len(html),
        "title": (re.search(r"<title>(.*?)</title>", html, re.I) or [None, ""])[1],
        "has_safe_gate": "safe/js" in html or "safeid" in html,
        "has_cf_challenge": "challenge-platform" in html or "__CF$cv$params" in html,
        "has_discuz": any(k in html.lower() for k in ["discuz", "forumdisplay", "thread-", "fid"]),
        "has_age_warning": "满18岁" in html or "over 18" in html.lower(),
        "preview": html[:500].replace("\n", " "),
    }


async def test_httpx():
    results = []
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
    ) as client:
        for url in [BASE, FORUM_URL]:
            r = await client.get(url)
            results.append(analyze(f"httpx GET", r.text, str(r.url)))
    return results


async def test_playwright(headless: bool = True):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=UA, locale="zh-CN")
        page = await context.new_page()

        # Step 1: homepage
        await page.goto(BASE, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        html1 = await page.content()
        results.append(analyze("playwright homepage (3s wait)", html1, page.url))

        # Try click age verification if present
        clicked = False
        for sel in [
            "text=满18岁",
            "text=If you are over 18",
            "a.enter-btn",
            "#enter-btn",
            ".btn-enter",
        ]:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible(timeout=2000):
                    await el.click()
                    clicked = True
                    print(f"  [browser] clicked: {sel}")
                    break
            except Exception:
                pass

        if clicked:
            await page.wait_for_timeout(5000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

        html2 = await page.content()
        results.append(analyze("playwright after age click", html2, page.url))

        # Step 2: try forum.php
        await page.goto(FORUM_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        html3 = await page.content()
        results.append(analyze("playwright forum.php", html3, page.url))

        cookies = await context.cookies()
        print(f"  [browser] cookies count: {len(cookies)}")
        for c in cookies[:8]:
            print(f"    - {c['name']}: {c['value'][:40]}...")

        await browser.close()
    return results


def print_results(results):
    print("\n" + "=" * 70)
    for r in results:
        print(f"\n[{r['label']}]")
        print(f"  URL:     {r['url']}")
        print(f"  Length:  {r['length']} bytes")
        print(f"  Title:   {r['title']}")
        print(f"  Safe gate:    {r['has_safe_gate']}")
        print(f"  CF challenge: {r['has_cf_challenge']}")
        print(f"  Discuz/forum: {r['has_discuz']}")
        print(f"  Age warning:  {r['has_age_warning']}")
        print(f"  Preview: {r['preview'][:200]}...")


async def main():
    print("=== HTTP (httpx) test ===")
    http_results = await test_httpx()
    print_results(http_results)

    print("\n\n=== Browser (Playwright) test ===")
    browser_results = await test_playwright(headless=True)
    print_results(browser_results)

    http_ok = any(r["has_discuz"] and not r["has_safe_gate"] for r in http_results)
    browser_ok = any(r["has_discuz"] and not r["has_safe_gate"] for r in browser_results)

    print("\n" + "=" * 70)
    print("CONCLUSION:")
    print(f"  HTTP can get real forum content:    {'YES' if http_ok else 'NO'}")
    print(f"  Browser can get real forum content: {'YES' if browser_ok else 'NO (may need manual CF verify or cookies)'}")
    if not http_ok:
        print("  -> Plain HTTP only returns JS gate / Cloudflare challenge page (~2.3KB)")
    if browser_ok and not http_ok:
        print("  -> Browser required; recommend Playwright + persistent cookie context")


if __name__ == "__main__":
    asyncio.run(main())
