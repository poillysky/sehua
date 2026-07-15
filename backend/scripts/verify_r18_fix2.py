"""Verify browser-first Fetcher can load board list pages."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.session import BASE_URL, SessionManager


async def main() -> None:
    sm = SessionManager()
    try:
        await sm.bootstrap(force=True)
        f = Fetcher(sm)
        for url in (
            f"{BASE_URL}forum-2-1.html",
            f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats",
            f"{BASE_URL}forum-36-1.html",
        ):
            html = await f.get_html(url, retries=2)
            ok = "Powered by Discuz" in html and not SessionManager.is_safe_shell(html)
            print(f"{'OK' if ok else 'FAIL'} len={len(html)} {url}")
            if not ok:
                raise SystemExit(1)
        print("all ok")
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
