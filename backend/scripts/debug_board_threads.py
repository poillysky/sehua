import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.parser import parse_forum_list
from crawler.session import BASE_URL, SessionManager


async def dump(fid: int, url: str, sm: SessionManager) -> None:
    f = Fetcher(sm)
    html = await f.get_html(url)
    Path(f"data/list_{fid}.html").write_text(html, encoding="utf-8")
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    print("=" * 60)
    print("fid", fid, "url", url)
    print("title", re.sub(r"\s+", " ", title.group(1)).strip() if title else None)
    print("len", len(html), "threadlist", "threadlist" in html.lower())
    print("stickthread_", len(re.findall(r"stickthread_", html, re.I)))
    print("normalthread_", len(re.findall(r"normalthread_", html, re.I)))

    threads = parse_forum_list(html, skip_sticky=False)
    for i, t in enumerate(threads[:20]):
        print(f"{i:02d} sticky={t.is_sticky} tid={t.tid} {(t.title or '')[:60]}")

    # Show tbody ids around first threads
    for m in re.finditer(r'<tbody[^>]*id="([^"]+)"', html, re.I):
        tid_in = re.search(r"(\d+)", m.group(1))
        if tid_in and any(str(t.tid) == tid_in.group(1) for t in threads[:8]):
            print(" tbody", m.group(1))


async def main() -> None:
    sm = SessionManager()
    try:
        await sm.bootstrap()
        await dump(2, f"{BASE_URL}forum-2-1.html", sm)
        await dump(103, f"{BASE_URL}forum-103-1.html", sm)
        # heat page raw markers
        html = await Fetcher(sm).get_html(
            f"{BASE_URL}forum.php?mod=forumdisplay&fid=2&filter=heat&orderby=heats"
        )
        Path("data/list_2_heat.html").write_text(html, encoding="utf-8")
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        print("=" * 60)
        print("HEAT title", re.sub(r"\s+", " ", title.group(1)).strip() if title else None)
        print(
            "HEAT len",
            len(html),
            "normalthread",
            len(re.findall(r"normalthread_", html, re.I)),
            "thread-",
            len(re.findall(r"thread-\d+", html)),
        )
        # any obfuscated link?
        print("sample hrefs", re.findall(r'href="([^"]{10,80})"', html)[:15])
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
