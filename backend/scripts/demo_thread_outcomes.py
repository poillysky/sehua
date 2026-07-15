"""Demo ed2k-aligned thread outcomes on 综合讨论区·情色分享 posts."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.parser import parse_forum_list
from crawler.session import BASE_URL, SessionManager
from parsers.boards import DISCUZ_BOARD_FID, DISCUZ_SHARE_TYPEID
from workers.thread_outcome import judge_thread_html


async def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    list_url = (
        f"{BASE_URL}forum.php?mod=forumdisplay&fid={DISCUZ_BOARD_FID}"
        f"&filter=typeid&typeid={DISCUZ_SHARE_TYPEID}&orderby=dateline&page=1"
    )
    sm = SessionManager()
    f = Fetcher(sm)
    try:
        list_html = await f.get_list_html(list_url)
        threads = parse_forum_list(list_html, skip_sticky=True)[:5]
        f.set_referer(list_url)
        print(f"样例 {len(threads)} 帖 · 综合讨论区/情色分享\n")
        for th in threads:
            tid = th.tid
            html = await f.get_thread_html(f"{BASE_URL}thread-{tid}-1-1.html")
            out = judge_thread_html(html, board_fid=DISCUZ_BOARD_FID, list_title=th.title or "")
            print(
                f"tid={tid}  [{out.label}]  {out.outcome}"
                + (f"  附件={out.attachment_kind}" if out.need_attachments else "")
            )
            print(f"  标题: {(out.title or th.title or '')[:70]}")
            print()
    finally:
        await sm.close()


if __name__ == "__main__":
    asyncio.run(main())
