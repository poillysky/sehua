"""Smoke: browser list + HTTP thread read one normal post."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher, detect_fetch_mode
from crawler.session import BASE_URL, SessionManager
from parsers.links import parse_thread_dual

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
POST_RE = re.compile(r'id="postmessage_[^"]*"[^>]*>(.*?)</div>', re.I | re.S)


async def main() -> None:
    sm = SessionManager()
    f = Fetcher(sm)
    list_url = f"{BASE_URL}forum-2-1.html"
    try:
        print("1) browser bootstrap + list...")
        list_html = await f.get_list_html(list_url)
        tids: list[str] = []
        seen: set[str] = set()
        for t in re.findall(r"thread-(\d+)-1-1\.html", list_html):
            if t not in seen:
                seen.add(t)
                tids.append(t)
        print(
            f"   list len={len(list_html)} "
            f"discuz={'Powered by Discuz' in list_html} "
            f"tids={tids[:5]}"
        )
        if not tids:
            print("RESULT FAIL: no tids")
            return

        tid = tids[0]
        turl = f"{BASE_URL}thread-{tid}-1-1.html"
        print(f"2) HTTP read thread mode={detect_fetch_mode(turl)} tid={tid}")
        f.set_referer(list_url)
        html = await f.get_thread_html(turl)

        title_m = TITLE_RE.search(html or "")
        title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:80] if title_m else ""
        has_discuz = "Powered by Discuz" in html
        has_post = "postmessage" in html
        shell = "var safeid" in (html or "")[:8000] and len(html) < 12000
        print(
            f"   len={len(html)} discuz={has_discuz} "
            f"postmessage={has_post} r18_shell={shell}"
        )
        print(f"   title={title!r}")

        pm = POST_RE.search(html or "")
        if pm:
            text = re.sub(r"<[^>]+>", " ", pm.group(1))
            text = re.sub(r"\s+", " ", text).strip()[:200]
            print(f"   post_snippet={text!r}")
        else:
            print("   post_snippet=(not found)")

        parsed = parse_thread_dual(html, tid=int(tid), preferred_link="magnet")
        print(
            f"3) parse magnets={len(parsed.magnets)} "
            f"ed2k={len(parsed.ed2k_links)} primary={parsed.primary_link_kind}"
        )
        if parsed.magnets:
            print(f"   magnet0={parsed.magnets[0][:90]}...")

        ok = has_discuz and has_post and not shell
        print("RESULT", "OK" if ok else "FAIL")
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
