"""Show HTTP-fetched posts from 综合讨论区 · 情色分享 (fid=95, typeid=716)."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.parser import parse_forum_list
from crawler.session import BASE_URL, SessionManager
from parsers.boards import DISCUZ_BOARD_FID, DISCUZ_SHARE_TYPEID, get_board_policy
from parsers.links import parse_thread_dual

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
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def list_url() -> str:
    return (
        f"{BASE_URL}forum.php?mod=forumdisplay&fid={DISCUZ_BOARD_FID}"
        f"&filter=typeid&typeid={DISCUZ_SHARE_TYPEID}&orderby=dateline&page=1"
    )


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pol = get_board_policy(DISCUZ_BOARD_FID)
    url = list_url()
    sm = SessionManager()
    f = Fetcher(sm)
    try:
        print(f"板块: {pol.name} · 情色分享 (fid={DISCUZ_BOARD_FID}, typeid={DISCUZ_SHARE_TYPEID})")
        print(f"列表: {url}")
        print("取页: 浏览器读列表 → HTTP 读帖\n")

        list_html = await f.get_list_html(url)
        threads = parse_forum_list(list_html, skip_sticky=True)
        print(f"列表帖数(跳过置顶): {len(threads)}")
        if not threads:
            print("列表为空")
            return

        f.set_referer(url)
        show_n = min(3, len(threads))
        for i, th in enumerate(threads[:show_n], 1):
            tid = th.tid
            turl = f"{BASE_URL}thread-{tid}-1-1.html"
            html = await f.get_thread_html(turl)
            title_m = TITLE_RE.search(html or "")
            title = clean_html(title_m.group(1) if title_m else "")
            if " - " in title:
                title = title.rsplit(" - ", 2)[0].strip()
            pm = POST_RE.search(html or "")
            body = clean_html(pm.group(1) if pm else "")[:800]
            parsed = parse_thread_dual(html, tid=int(tid), preferred_link=pol.primary_link)
            print("=" * 60)
            print(f"[{i}] 帖号 {tid}")
            print(f"标题: {title}")
            print(f"链接: {turl}")
            print(
                f"解析: magnet={len(parsed.magnets)} ed2k={len(parsed.ed2k_links)} "
                f"主链={parsed.primary_link_kind}"
            )
            print("--- 正文 ---")
            print(body if body else "(无正文)")
            print()
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
