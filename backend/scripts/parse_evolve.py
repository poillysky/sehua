"""合集识别进化 CLI：分类 → 单帖爬验 → 状态推进。

参见 docs/识别进化流程.md

Usage:
  python scripts/parse_evolve.py classify [--source pending|resources]
  python scripts/parse_evolve.py status
  python scripts/parse_evolve.py next --bucket 国产合集
  python scripts/parse_evolve.py run-one --bucket 国产合集 [--persist]
  python scripts/parse_evolve.py run-one --tid 123 [--persist]
  python scripts/parse_evolve.py pass --tid 123 --note "..."
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _tid_from_url(url: str) -> int:
    m = re.search(r"tid=(\d+)", url or "")
    return int(m.group(1)) if m else 0


def cmd_classify(args: argparse.Namespace) -> int:
    from parsers.evolution import (
        classify_title,
        load_state,
        recompute_buckets,
        save_state,
        upsert_post,
    )

    forum_id = args.forum
    state = load_state()
    state["forum_id"] = forum_id

    rows: list[dict] = []
    if args.source == "pending":
        from db.connection import connect

        conn = connect()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT url, COALESCE(thread_title, ''), tid, board_fid
            FROM crawl_pages
            WHERE forum_id = %s
              AND page_type = 'thread'
              AND status = 'pending'
            ORDER BY updated_at DESC NULLS LAST
            LIMIT %s
            """,
            (forum_id, args.limit),
        )
        for url, title, tid, board_fid in cur.fetchall():
            tid_i = int(tid or 0) or _tid_from_url(url)
            if not tid_i:
                continue
            rows.append(
                {
                    "tid": tid_i,
                    "url": url,
                    "title": title or "",
                    "board_fid": str(board_fid or ""),
                    "hash": "",
                }
            )
        conn.close()
        # pending 常缺 thread_title：用资源库标题补全，便于分类
        need = [r for r in rows if not (r["title"] or "").strip()]
        if need:
            from db.resource_db import connect_resource

            rconn = connect_resource()
            rcur = rconn.cursor()
            for r in need:
                rcur.execute(
                    """
                    SELECT MAX(title) FROM resource_sources
                    WHERE forum_id = %s AND source_url LIKE %s
                    """,
                    (forum_id, f"%tid={r['tid']}%"),
                )
                hit = rcur.fetchone()
                if hit and hit[0]:
                    r["title"] = hit[0]
            rconn.close()
    else:
        from db.resource_db import connect_resource

        conn = connect_resource()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
              BTRIM(rs.source_url) AS url,
              MAX(rs.title) AS title,
              (ARRAY_AGG(rs.hash ORDER BY r.updated_at DESC NULLS LAST))[1] AS hash,
              MAX(rs.board_fid) AS board_fid
            FROM resource_sources rs
            JOIN ed2k_resources r ON r.hash = rs.hash
            WHERE rs.forum_id = %s
              AND NULLIF(BTRIM(COALESCE(rs.source_url, '')), '') IS NOT NULL
            GROUP BY 1
            ORDER BY MAX(r.updated_at) DESC NULLS LAST
            LIMIT %s
            """,
            (forum_id, args.limit),
        )
        for url, title, hash_, board_fid in cur.fetchall():
            tid_i = _tid_from_url(url)
            if not tid_i:
                continue
            rows.append(
                {
                    "tid": tid_i,
                    "url": url,
                    "title": title or "",
                    "board_fid": str(board_fid or ""),
                    "hash": hash_ or "",
                }
            )
        conn.close()

    added = 0
    for row in rows:
        tid = str(row["tid"])
        existing = (state.get("posts") or {}).get(tid)
        if existing and existing.get("status") == "passed" and not args.reset_passed:
            continue
        bucket = classify_title(row["title"])
        status = "pending"
        if existing and existing.get("status") in ("failed", "passed") and not args.reset_passed:
            # keep progress; refresh metadata
            status = existing["status"]
        upsert_post(
            state,
            {
                "tid": int(row["tid"]),
                "url": row["url"],
                "title": row["title"][:200],
                "bucket": bucket,
                "hash": row.get("hash") or (existing or {}).get("hash") or "",
                "board_fid": row.get("board_fid") or "",
                "status": status,
            },
        )
        added += 1

    buckets = recompute_buckets(state)
    path = save_state(state)
    print("classified_rows", len(rows), "upserted", added)
    print("buckets", json.dumps(buckets, ensure_ascii=False, indent=2))
    print("state", path)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    from parsers.evolution import load_state, recompute_buckets

    state = load_state()
    buckets = recompute_buckets(state)
    print("forum", state.get("forum_id"), "active_bucket", state.get("active_bucket"))
    print("posts", len(state.get("posts") or {}))
    for name, c in sorted(buckets.items(), key=lambda x: -x[1].get("total", 0)):
        done = c["passed"] == c["total"] and c["total"] > 0
        mark = "DONE" if done else "...."
        print(
            f"  [{mark}] {name}: total={c['total']} passed={c['passed']} "
            f"failed={c['failed']} skipped={c.get('skipped', 0)} pending={c['pending']}"
        )
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    from parsers.evolution import load_state, next_in_bucket, save_state

    state = load_state()
    bucket = args.bucket or state.get("active_bucket")
    if not bucket:
        print("need --bucket")
        return 2
    state["active_bucket"] = bucket
    item = next_in_bucket(state, bucket)
    save_state(state)
    if not item:
        print("bucket_empty_or_all_passed", bucket)
        return 0
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


async def _fetch_html(url: str) -> str:
    from db.connection import connect
    from db.forum_configs import load_forum_configs_map
    from workers.session_factory import fetcher_from_config, session_from_config

    conn = connect()
    try:
        cfg = load_forum_configs_map(conn).get("2048") or {}
    finally:
        conn.close()
    session = session_from_config(cfg)
    fetcher = fetcher_from_config(session, cfg)
    await session.bootstrap()
    fetcher.set_referer(url)
    try:
        return await fetcher.get_thread_html(url, retries=2) or ""
    except Exception:
        await session.bootstrap(force=True)
        return await fetcher.get_thread_html(url, retries=2) or ""


async def _run_one_async(args: argparse.Namespace) -> int:
    from parsers.evolution import (
        classify_title,
        judge_html,
        load_state,
        next_in_bucket,
        recompute_buckets,
        save_state,
        upsert_post,
    )

    state = load_state()
    item = None
    if args.tid:
        item = (state.get("posts") or {}).get(str(args.tid))
        if not item:
            # synthesize from resources
            from db.resource_db import connect_resource

            conn = connect_resource()
            cur = conn.cursor()
            cur.execute(
                """
                SELECT BTRIM(rs.source_url), MAX(rs.title),
                       (ARRAY_AGG(rs.hash ORDER BY r.updated_at DESC NULLS LAST))[1],
                       MAX(rs.board_fid)
                FROM resource_sources rs
                JOIN ed2k_resources r ON r.hash = rs.hash
                WHERE rs.forum_id = %s AND rs.source_url LIKE %s
                GROUP BY 1
                LIMIT 1
                """,
                (state.get("forum_id") or "2048", f"%tid={args.tid}%"),
            )
            row = cur.fetchone()
            conn.close()
            if not row:
                print("tid_not_found", args.tid)
                return 2
            item = {
                "tid": int(args.tid),
                "url": row[0],
                "title": row[1] or "",
                "hash": row[2] or "",
                "board_fid": str(row[3] or ""),
                "bucket": classify_title(row[1] or ""),
                "status": "pending",
            }
    elif args.url:
        tid = _tid_from_url(args.url)
        item = {
            "tid": tid,
            "url": args.url,
            "title": "",
            "hash": args.hash or "",
            "board_fid": "",
            "bucket": args.bucket or "?",
            "status": "pending",
        }
    else:
        bucket = args.bucket or state.get("active_bucket")
        if not bucket:
            print("need --bucket or --tid")
            return 2
        state["active_bucket"] = bucket
        item = next_in_bucket(state, bucket)
        if not item:
            print("no_next_in_bucket", bucket)
            recompute_buckets(state)
            save_state(state)
            return 0

    tid = int(item["tid"])
    url = item["url"]
    print(f"run-one tid={tid} bucket={item.get('bucket')} url={url}", flush=True)

    html = await _fetch_html(url)
    if not html or len(html) < 500:
        print("fetch_failed", tid, "len", len(html or ""))
        upsert_post(
            state,
            {
                **item,
                "status": "failed",
                "issues": ["fetch_failed"],
                "last_judge": None,
            },
        )
        save_state(state)
        return 1

    html_path = ROOT / f"_tmp_evolve_{tid}.html"
    html_path.write_text(html, encoding="utf-8")

    board_fid = str(item.get("board_fid") or "103")
    judgment = judge_html(html, tid=tid, board_fid=board_fid)
    if not item.get("bucket") or item.get("bucket") == "?":
        item["bucket"] = classify_title(judgment.get("parsed_title") or item.get("title") or "")

    ok = bool(judgment.get("ok"))
    issues = list(judgment.get("issues") or [])
    status = "passed" if ok else "failed"
    # 购买隐藏 / 无磁力：不算解析失败，标记 skipped 继续下一帖
    if "empty_assets" in issues:
        html_l = html.lower()
        soft_shell = (
            "magnet:" not in html_l
            and "body{font-size" in html_l
            and ("| 最新合集" in html or "人人为我论坛" in html)
        )
        gated = ("购买本帖" in html) or ("購買本帖" in html)
        try:
            from workers.thread_outcome import judge_thread_html

            tout = judge_thread_html(
                html,
                board_fid=board_fid,
                forum_id=str(state.get("forum_id") or "2048"),
                preferred_link="magnet",
            )
            verdict = str(tout.verdict or "")
            outcome = str(tout.outcome or "")
            if verdict == "need_attachments" or "购买" in outcome:
                gated = True
            if verdict in ("stub",) and "购买" in html:
                gated = True
        except Exception:
            pass
        if soft_shell and not gated:
            print("soft_shell detected, retry fetch once...", flush=True)
            html2 = await _fetch_html(url)
            if html2 and len(html2) > 500 and "magnet:" in html2.lower():
                html = html2
                html_path.write_text(html, encoding="utf-8")
                judgment = judge_html(html, tid=tid, board_fid=board_fid)
                issues = list(judgment.get("issues") or [])
                ok = bool(judgment.get("ok"))
                status = "passed" if ok else "failed"
            else:
                status = "failed"
                ok = False
                issues = list(dict.fromkeys([*issues, "soft_shell_html"]))
        elif "empty_assets" in issues:
            if gated:
                status = "skipped"
                ok = True
            else:
                status = "failed"
                ok = False
    upsert_post(
        state,
        {
            **item,
            "title": (judgment.get("parsed_title") or item.get("title") or "")[:200],
            "status": status,
            "issues": issues,
            "last_judge": judgment,
            "html_path": str(html_path),
        },
    )
    recompute_buckets(state)
    save_state(state)

    report = {
        "tid": tid,
        "url": url,
        "bucket": item.get("bucket"),
        "ok": status == "passed",
        "status": status,
        "issues": issues,
        "metrics": judgment.get("metrics"),
        "html_path": str(html_path),
        "persist": False,
    }

    if args.persist and item.get("hash") and status == "passed":
        from workers.recrawl import recrawl_imported_resources

        print("persist recrawl hash", item["hash"][:16], "...", flush=True)
        result = await recrawl_imported_resources([item["hash"]])
        report["persist"] = True
        report["persist_result"] = {
            "ok": result.get("ok"),
            "imported": result.get("imported"),
            "failed": result.get("failed"),
            "mode": result.get("mode"),
        }

    out_path = ROOT / "_tmp_evolve_last.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    if status == "skipped":
        print(f"SKIP issues={issues} (gated/empty; not a parse bug)")
        print("metrics", json.dumps(judgment.get("metrics"), ensure_ascii=False))
        print("->", out_path)
        print("OK: skip to next post in bucket", item.get("bucket"))
        return 0
    mark = "PASS" if status == "passed" else "FAIL"
    print(f"{mark} issues={issues}")
    print("metrics", json.dumps(judgment.get("metrics"), ensure_ascii=False))
    print("->", out_path)
    if status != "passed":
        print("STOP: fix parsers using", html_path, "then re-run same --tid", tid)
        return 1
    print("OK: proceed to next post in bucket", item.get("bucket"))
    return 0


def cmd_run_one(args: argparse.Namespace) -> int:
    return asyncio.run(_run_one_async(args))


def cmd_pass(args: argparse.Namespace) -> int:
    from parsers.evolution import load_state, recompute_buckets, save_state, upsert_post

    state = load_state()
    tid = str(args.tid)
    prev = (state.get("posts") or {}).get(tid)
    if not prev:
        print("tid_not_in_state", tid)
        return 2
    upsert_post(
        state,
        {
            **prev,
            "status": "passed",
            "issues": [],
            "manual_pass_note": args.note or "manual",
        },
    )
    recompute_buckets(state)
    save_state(state)
    print("manual_passed", tid, args.note or "")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse evolution: classify → one-post judge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cls = sub.add_parser("classify", help="classify pending/resources into buckets")
    p_cls.add_argument("--forum", default="2048")
    p_cls.add_argument("--source", choices=["pending", "resources"], default="pending")
    p_cls.add_argument("--limit", type=int, default=8000)
    p_cls.add_argument(
        "--reset-passed",
        action="store_true",
        help="re-open already passed posts as pending",
    )
    p_cls.set_defaults(func=cmd_classify)

    p_st = sub.add_parser("status", help="show bucket progress")
    p_st.set_defaults(func=cmd_status)

    p_nx = sub.add_parser("next", help="show next post in bucket")
    p_nx.add_argument("--bucket", default=None)
    p_nx.set_defaults(func=cmd_next)

    p_run = sub.add_parser("run-one", help="crawl + judge one post; stop on fail")
    p_run.add_argument("--bucket", default=None)
    p_run.add_argument("--tid", type=int, default=None)
    p_run.add_argument("--url", default=None)
    p_run.add_argument("--hash", default=None)
    p_run.add_argument(
        "--persist",
        action="store_true",
        help="also recrawl+replace into resource DB after fetch",
    )
    p_run.set_defaults(func=cmd_run_one)

    p_pass = sub.add_parser("pass", help="manually mark tid passed")
    p_pass.add_argument("--tid", type=int, required=True)
    p_pass.add_argument("--note", default="")
    p_pass.set_defaults(func=cmd_pass)

    args = ap.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
