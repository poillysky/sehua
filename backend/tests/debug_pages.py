import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.fetcher import Fetcher
from crawler.session import SessionManager


async def main():
    s = SessionManager()
    f = Fetcher(s)
    await s.bootstrap()
    html = await f.get_html("https://www.sehuatang.net/forum-142-2.html")
    hrefs = re.findall(r'href="([^"]*thread[^"]*)"', html, re.I)
    print("thread hrefs count", len(hrefs))
    for h in hrefs[:15]:
        print(" ", h[:100])
    # also viewthread
    vts = re.findall(r"viewthread&amp;tid=(\d+)", html)
    print("viewthread tids", len(vts), vts[:5])


asyncio.run(main())
