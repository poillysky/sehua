#!/usr/bin/env python3
"""Test crawler: read threads from a specified forum section."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.fetcher import FetchError, Fetcher
from crawler.parser import (
    is_valid_forum_list,
    is_valid_thread,
    parse_forum_list,
    parse_thread,
)
from crawler.session import BASE_URL, SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("run_test")


async def run_test(fid: int, page: int, limit: int, force_bootstrap: bool) -> int:
    session = SessionManager()
    fetcher = Fetcher(session)

    print("=" * 60)
    print(f"  板块读帖测试  fid={fid}  page={page}  limit={limit}")
    print("=" * 60)

    # Step 1: bootstrap session
    t0 = time.perf_counter()
    await session.bootstrap(force=force_bootstrap)
    print(f"\n[1/3] Session ready ({time.perf_counter() - t0:.1f}s)")
    print(f"      cookies: {', '.join(session.cookies.keys())}")

    # Step 2: fetch forum list
    list_url = f"{BASE_URL}forum-{fid}-{page}.html"
    fetcher.set_referer(f"{BASE_URL}forum.php")
    print(f"\n[2/3] Fetching forum list: {list_url}")

    try:
        list_html = await fetcher.get_html(list_url)
    except FetchError as e:
        log.error("Forum list fetch failed: %s", e)
        return 1

    if not is_valid_forum_list(list_html):
        log.error("Forum list page invalid (len=%d)", len(list_html))
        return 1

    threads = parse_forum_list(list_html)
    if not threads:
        log.error("No threads found on forum page")
        return 1

    print(f"      Found {len(threads)} threads, will read {min(limit, len(threads))}")

    # Step 3: read thread details
    print(f"\n[3/3] Reading threads...")
    fetcher.set_referer(list_url)

    ok, fail = 0, 0
    results = []

    for i, brief in enumerate(threads[:limit]):
        t_start = time.perf_counter()
        try:
            html = await fetcher.get_html(brief.url)
            if not is_valid_thread(html):
                raise FetchError(f"Invalid thread page (len={len(html)})")

            detail = parse_thread(html, brief.tid)
            elapsed = time.perf_counter() - t_start

            if not detail.posts:
                raise FetchError("No posts parsed")

            ok += 1
            first = detail.posts[0]
            preview = first.content[:80] + ("..." if len(first.content) > 80 else "")
            results.append(
                {
                    "status": "OK",
                    "tid": brief.tid,
                    "title": detail.title or brief.title,
                    "author": first.author,
                    "floors": len(detail.posts),
                    "preview": preview,
                    "elapsed": elapsed,
                }
            )
        except (FetchError, Exception) as e:
            fail += 1
            results.append(
                {
                    "status": "FAIL",
                    "tid": brief.tid,
                    "title": brief.title,
                    "error": str(e),
                    "elapsed": time.perf_counter() - t_start,
                }
            )

        if i < limit - 1:
            await asyncio.sleep(1.5)

    # Print results
    print()
    for i, r in enumerate(results, 1):
        if r["status"] == "OK":
            print(f"  [{i}] OK   tid={r['tid']}")
            print(f"       title : {r['title'][:60]}")
            print(f"       author: {r['author'] or '(unknown)'}")
            print(f"       floors: {r['floors']}  ({r['elapsed']:.1f}s)")
            print(f"       preview: {r['preview']}")
        else:
            print(f"  [{i}] FAIL tid={r['tid']}")
            print(f"       title: {r['title'][:60]}")
            print(f"       error: {r['error']}")
        print()

    print("=" * 60)
    print(f"  RESULT: {ok} OK / {fail} FAIL / {ok + fail} total")
    if ok > 0 and fail == 0:
        print("  读帖正常 [PASS]")
    elif ok > 0:
        print(f"  读帖部分成功 [PARTIAL] ({ok}/{ok + fail})")
    else:
        print("  读帖异常 [FAIL]")
    print("=" * 60)

    return 0 if ok > 0 and fail == 0 else (0 if ok > 0 else 1)


def main():
    parser = argparse.ArgumentParser(description="Test reading posts from a sehuatang forum section")
    parser.add_argument("--fid", type=int, default=103, help="Forum section ID (default: 103)")
    parser.add_argument("--page", type=int, default=1, help="List page number (default: 1)")
    parser.add_argument("--limit", type=int, default=5, help="Number of threads to read (default: 5)")
    parser.add_argument(
        "--force-bootstrap",
        action="store_true",
        help="Force Playwright bootstrap even if cookies exist",
    )
    args = parser.parse_args()

    try:
        code = asyncio.run(
            run_test(
                fid=args.fid,
                page=args.page,
                limit=args.limit,
                force_bootstrap=args.force_bootstrap,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted.")
        code = 130

    sys.exit(code)


if __name__ == "__main__":
    main()
