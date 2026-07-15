"""Verify Fetcher can pass R18 on list pages after session/fetcher fix."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.session import BASE_URL, COOKIE_FILE, SessionManager


async def main() -> None:
    # 丢弃缺 safe=1 的旧 jar，强制走新 bootstrap
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()
        print("removed old cookies")

    sm = SessionManager()
    await sm.bootstrap(force=True)
    f = Fetcher(sm)
    urls = [
        f"{BASE_URL}forum-2-1.html",
        f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats",
        f"{BASE_URL}forum-36-1.html",
    ]
    for url in urls:
        html = await f.get_html(url)
        ok = "Powered by Discuz" in html and "var safeid" not in html
        print(f"{'OK' if ok else 'FAIL'} len={len(html)} {url}")
        if not ok:
            raise SystemExit(1)
    print("all ok")


if __name__ == "__main__":
    asyncio.run(main())
