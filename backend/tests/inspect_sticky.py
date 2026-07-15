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
    html = await f.get_html("https://www.sehuatang.net/forum-142-1.html")
    for pat in [r'tbody id="([^"]+)"', r'class="([^"]*stick[^"]*)"', r"thread-(\d+)-1-1"]:
        ms = re.findall(pat, html[:50000], re.I)
        print(pat, "count", len(ms), "sample", ms[:8])
    # show first 3 tbody ids with thread links
    for m in re.finditer(r'<tbody[^>]*id="([^"]*)"[^>]*>(.*?)</tbody>', html, re.I | re.S):
        tid = re.search(r"thread-(\d+)-1-1", m.group(2))
        if tid:
            print("tbody", m.group(1), "tid", tid.group(1))


asyncio.run(main())
