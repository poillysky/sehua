#!/usr/bin/env python3
"""Batch read forum threads with real-time preview output."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.fetcher import FetchError, Fetcher
from crawler.parser import is_valid_forum_list, is_valid_thread, parse_forum_list, parse_thread
from crawler.session import BASE_URL, SessionManager

log = logging.getLogger("read_batch")


def setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def safe_print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def preview(text: str, n: int = 40) -> str:
    return text.replace("\n", " ").strip()[:n]


async def collect_threads(
    fetcher: Fetcher,
    fid: int,
    need_count: int,
) -> list:
    """Paginate forum list until we have enough thread entries."""
    all_threads = []
    page = 1
    max_pages = 30
    seen_tids: set[int] = set()

    while len(all_threads) < need_count and page <= max_pages:
        list_url = f"{BASE_URL}forum-{fid}-{page}.html"
        prev_url = f"{BASE_URL}forum-{fid}-{page - 1}.html" if page > 1 else f"{BASE_URL}forum.php"
        fetcher.set_referer(prev_url)
        try:
            list_html = await fetcher.get_html(list_url)
        except FetchError as e:
            log.warning("List page %d failed: %s", page, e)
            if page == 1:
                raise
            break

        if not is_valid_forum_list(list_html):
            if page == 1:
                raise FetchError(f"Invalid forum list fid={fid}")
            break

        batch = parse_forum_list(list_html, skip_sticky=False)
        new_items = [t for t in batch if t.tid not in seen_tids]
        for t in new_items:
            seen_tids.add(t.tid)
        all_threads.extend(new_items)

        safe_print(f"  列表第{page}页: +{len(new_items)} 条 (累计 {len(all_threads)})")

        if not new_items:
            break
        page += 1
        await asyncio.sleep(0.6)

    return all_threads


async def run(fid: int, start: int, limit: int, delay: float, force_bootstrap: bool) -> int:
    session = SessionManager()
    fetcher = Fetcher(session)
    await session.bootstrap(force=force_bootstrap)

    need = start - 1 + limit
    safe_print(f"收集 fid={fid} 帖子列表 (至少需要 {need} 条)...")
    threads = await collect_threads(fetcher, fid, need)

    if len(threads) < start:
        safe_print(f"列表不足: 仅 {len(threads)} 条，无法从第 {start} 条开始")
        return 1

    targets = threads[start - 1 : start - 1 + limit]
    actual = len(targets)
    safe_print(f"\n从第 {start} 条起读取 {actual} 帖 (请求 {limit} 帖)\n")
    safe_print("=" * 72)

    ok, fail = 0, 0
    rows = []
    fetcher.set_referer(f"{BASE_URL}forum-{fid}-1.html")
    t0 = time.perf_counter()

    for i, brief in enumerate(targets, start=start):
        t1 = time.perf_counter()
        try:
            html = await fetcher.get_html(brief.url)
            if not is_valid_thread(html):
                raise FetchError(f"invalid page len={len(html)}")
            detail = parse_thread(html, brief.tid)
            if not detail.posts:
                raise FetchError("empty body")
            body = detail.posts[0].content
            title = detail.title or brief.title
            p40 = preview(body, 40)
            ok += 1
            safe_print(f"[{i:>3}] OK   tid={brief.tid}")
            safe_print(f"       标题: {title[:60]}")
            safe_print(f"       正文: {p40}")
            rows.append({"idx": i, "tid": brief.tid, "title": title, "preview40": p40, "status": "OK"})
        except Exception as e:
            fail += 1
            err = str(e) or type(e).__name__
            safe_print(f"[{i:>3}] FAIL tid={brief.tid}")
            safe_print(f"       标题: {brief.title[:60]}")
            safe_print(f"       错误: {err}")
            rows.append({"idx": i, "tid": brief.tid, "title": brief.title, "preview40": "", "status": f"FAIL: {err}"})
        safe_print(f"       ({time.perf_counter() - t1:.1f}s)")
        safe_print("-" * 72)

        if i < start + len(targets) - 1:
            await asyncio.sleep(delay)

    elapsed = time.perf_counter() - t0
    safe_print("=" * 72)
    safe_print(f"完成: {ok} OK / {fail} FAIL / {ok + fail} total  耗时 {elapsed:.0f}s")

    out = ROOT / "data" / f"batch_{fid}_s{start}_n{limit}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"fid": fid, "start": start, "limit": limit, "ok": ok, "fail": fail, "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    safe_print(f"结果已保存: {out}")
    return 0 if ok > 0 else 1


def main():
    setup_stdout()
    parser = argparse.ArgumentParser(description="Batch read forum threads with live preview")
    parser.add_argument("--fid", type=int, required=True)
    parser.add_argument("--start", type=int, default=12, help="从第几条开始 (1-based)")
    parser.add_argument("--limit", type=int, default=100, help="读取条数")
    parser.add_argument("--delay", type=float, default=1.0, help="请求间隔秒")
    parser.add_argument("--force-bootstrap", action="store_true")
    parser.add_argument("-q", "--quiet-log", action="store_true")
    args = parser.parse_args()

    level = logging.WARNING if args.quiet_log else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    try:
        code = asyncio.run(run(args.fid, args.start, args.limit, args.delay, args.force_bootstrap))
    except KeyboardInterrupt:
        safe_print("\n已中断")
        code = 130
    except FetchError as e:
        safe_print(f"错误: {e}")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
