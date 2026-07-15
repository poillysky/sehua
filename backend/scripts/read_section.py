#!/usr/bin/env python3
"""List all forum sections and read consecutive threads from 网友转帖区."""

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
from crawler.forum_index import find_forum_by_name, parse_forum_index
from crawler.parser import is_valid_forum_list, is_valid_thread, parse_forum_list, parse_thread
from crawler.session import BASE_URL, SessionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("read_forum")


def preview_20(text: str) -> str:
    text = text.replace("\n", " ").strip()
    return text[:20]


async def list_all_forums(fetcher: Fetcher) -> list:
    fetcher.set_referer(BASE_URL)
    html = await fetcher.get_html(f"{BASE_URL}forum.php")
    return parse_forum_index(html)


async def read_section_threads(
    fetcher: Fetcher,
    fid: int,
    page: int,
    limit: int,
    delay: float,
) -> tuple[int, int, list[dict]]:
    list_url = f"{BASE_URL}forum-{fid}-{page}.html"
    fetcher.set_referer(f"{BASE_URL}forum.php")
    list_html = await fetcher.get_html(list_url)

    if not is_valid_forum_list(list_html):
        raise FetchError(f"Invalid forum list page fid={fid} page={page}")

    threads = parse_forum_list(list_html, skip_sticky=True)
    if not threads:
        raise FetchError(f"No threads on fid={fid} page={page}")

    fetcher.set_referer(list_url)
    ok, fail = 0, 0
    rows: list[dict] = []

    for idx, brief in enumerate(threads[:limit], start=1):
        try:
            html = await fetcher.get_html(brief.url)
            if not is_valid_thread(html):
                raise FetchError("invalid thread page")
            detail = parse_thread(html, brief.tid)
            if not detail.posts:
                raise FetchError("no post body")
            body = detail.posts[0].content
            ok += 1
            rows.append(
                {
                    "idx": idx,
                    "tid": brief.tid,
                    "title": detail.title or brief.title,
                    "preview20": preview_20(body),
                    "status": "OK",
                }
            )
        except Exception as e:
            fail += 1
            rows.append(
                {
                    "idx": idx,
                    "tid": brief.tid,
                    "title": brief.title,
                    "preview20": "",
                    "status": f"FAIL: {e}",
                }
            )
        if idx < min(limit, len(threads)):
            await asyncio.sleep(delay)

    return ok, fail, rows


async def main_async(args) -> int:
    session = SessionManager()
    fetcher = Fetcher(session)
    await session.bootstrap(force=args.force_bootstrap)

    print("=" * 70)
    print("  1. 网站板块统计")
    print("=" * 70)

    sections = await list_all_forums(fetcher)
    print(f"\n共 {len(sections)} 个板块 (fid 去重后):\n")
    for s in sections:
        parent = f" [{s.parent}]" if s.parent else ""
        print(f"  fid={s.fid:>4}  {s.name}{parent}")

    matches = find_forum_by_name(sections, args.section)
    if args.fid:
        target = next((s for s in sections if s.fid == args.fid), None)
        if not target:
            print(f"\n未找到 fid={args.fid}")
            return 1
    elif not matches:
        print(f"\n未找到名称包含「{args.section}」的板块")
        print("相关板块:")
        for s in sections:
            if "转帖" in s.name or "网友" in s.name:
                print(f"  fid={s.fid}  {s.name}")
        return 1
    else:
        target = matches[0]
        if len(matches) > 1:
            print(f"\n匹配到 {len(matches)} 个板块，使用第一个: fid={target.fid} {target.name}")
            for m in matches:
                print(f"  - fid={m.fid} {m.name}")

    print("\n" + "=" * 70)
    print(f"  2. 连续读帖: {target.name} (fid={target.fid})")
    print(f"     page={args.page}  limit={args.limit}")
    print("=" * 70 + "\n")

    t0 = time.perf_counter()
    ok, fail, rows = await read_section_threads(
        fetcher, target.fid, args.page, args.limit, args.delay
    )

    for r in rows:
        print(f"[{r['idx']:>2}] tid={r['tid']}")
        print(f"     标题: {r['title'][:55]}")
        if r["status"] == "OK":
            print(f"     正文前20字: {r['preview20']}")
        else:
            print(f"     状态: {r['status']}")
        print()

    print("=" * 70)
    print(f"  完成: {ok} OK / {fail} FAIL / {ok + fail} total  ({time.perf_counter() - t0:.1f}s)")
    print("=" * 70)

    # save utf-8 result file
    import json

    out_path = ROOT / "data" / f"read_{target.fid}_p{args.page}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "forum": {"fid": target.fid, "name": target.name},
                "page": args.page,
                "total_forums": len(sections),
                "results": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  结果已保存: {out_path}")
    return 0 if ok > 0 else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--section", default="转帖交流", help="板块名称关键词")
    parser.add_argument("--fid", type=int, default=0, help="直接指定 fid，优先于 --section")
    parser.add_argument("--page", type=int, default=1, help="列表页码")
    parser.add_argument("--limit", type=int, default=20, help="连续读取帖子数")
    parser.add_argument("--delay", type=float, default=1.2, help="请求间隔秒")
    parser.add_argument("--force-bootstrap", action="store_true")
    args = parser.parse_args()

    try:
        code = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        code = 130
    except FetchError as e:
        log.error("%s", e)
        code = 1

    sys.exit(code)


if __name__ == "__main__":
    main()
