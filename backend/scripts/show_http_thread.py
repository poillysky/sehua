"""Print title + post body for one HTTP-fetched thread (UTF-8 console)."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.session import BASE_URL, SessionManager

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
POST_RE = re.compile(r'id="postmessage_[^"]*"[^>]*>(.*?)</div>', re.I | re.S)


def clean_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</p>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&#160;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    sm = SessionManager()
    f = Fetcher(sm)
    list_url = f"{BASE_URL}forum-2-1.html"
    try:
        list_html = await f.get_list_html(list_url)
        tids: list[str] = []
        seen: set[str] = set()
        for t in re.findall(r"thread-(\d+)-1-1\.html", list_html):
            if t not in seen:
                seen.add(t)
                tids.append(t)

        # Prefer a resource thread if possible (later non-sticky-looking ids),
        # else first readable post.
        candidates = tids[:12]
        f.set_referer(list_url)
        chosen = None
        html = ""
        for tid in candidates:
            h = await f.get_thread_html(f"{BASE_URL}thread-{tid}-1-1.html")
            if "Powered by Discuz" in h and "postmessage" in h:
                # skip pure admin sticky without tags if later ones look better
                if "【" in h or "magnet" in h.lower() or "ed2k" in h.lower():
                    chosen, html = tid, h
                    break
                if chosen is None:
                    chosen, html = tid, h
        if not chosen:
            print("未读到帖子")
            return

        title_m = TITLE_RE.search(html or "")
        title = clean_html(title_m.group(1) if title_m else "")
        # Drop forum suffix after last " - "
        if " - " in title:
            title = title.rsplit(" - ", 2)[0].strip()

        pm = POST_RE.search(html or "")
        body = clean_html(pm.group(1) if pm else "")[:1500]

        print(f"帖号: {chosen}")
        print(f"地址: {BASE_URL}thread-{chosen}-1-1.html")
        print(f"标题: {title}")
        print("--- 正文 ---")
        print(body if body else "(无正文)")
        print("--- end ---")
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
