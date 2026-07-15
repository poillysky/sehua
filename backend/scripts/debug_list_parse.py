import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.parser import parse_forum_list
from crawler.session import BASE_URL, SessionManager


async def main() -> None:
    sm = SessionManager()
    try:
        await sm.bootstrap()
        f = Fetcher(sm)
        urls = [
            f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats",
            f"{BASE_URL}forum-2-1.html",
            f"{BASE_URL}forum.php?mod=forumdisplay&fid=95&filter=typeid&typeid=716&orderby=dateline&page=1",
            f"{BASE_URL}forum-142-1.html",
        ]
        for url in urls:
            html = await f.get_html(url)
            skip = parse_forum_list(html, skip_sticky=True)
            all_t = parse_forum_list(html, skip_sticky=False)
            tids = set(re.findall(r"thread-(\d+)-1-1\.html", html))
            view = set(re.findall(r"mod=viewthread&tid=(\d+)", html))
            print("---", url)
            print(
                "len",
                len(html),
                "parse_skip",
                len(skip),
                "parse_all",
                len(all_t),
                "regex",
                len(tids),
                "viewthread",
                len(view),
            )
            for t in (skip or all_t)[:5]:
                print(" ", t.tid, t.is_sticky, (t.title or "")[:50])
            Path("data/last_list.html").write_text(html, encoding="utf-8")
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
