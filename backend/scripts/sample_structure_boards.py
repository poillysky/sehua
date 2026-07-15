"""Sample a few live threads per board type to verify FORMAT_GUIDES copy."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from crawler.fetcher import Fetcher
from crawler.parser import parse_forum_list
from crawler.session import BASE_URL, SessionManager
from parsers.boards import BOARD_POLICIES
from parsers.content import parse_thread_content
from parsers.links import parse_thread_dual

SAMPLES = [
    (2, "magnet"),
    (36, "magnet"),
    (103, "magnet"),
    (152, "magnet"),
    (39, "magnet"),
    (95, "ed2k"),
    (141, "ed2k"),
    (142, "magnet"),
]

TAG_RE = re.compile(r"【\s*([^】]+?)\s*】")


def board_list_url(fid: int, page: int = 1) -> str:
    """Sampling uses list pages that actually expose posts.

    - typeid boards (fid=95) keep filter URL
    - others use SEO ``forum-{fid}-1.html`` (hot filter is crawl strategy; content same)
    """
    pol = BOARD_POLICIES[fid]
    if pol.list_typeid:
        return (
            f"{BASE_URL}forum.php?mod=forumdisplay&fid={fid}"
            f"&filter=typeid&typeid={pol.list_typeid}&orderby=dateline&page={page}"
        )
    return f"{BASE_URL}forum-{fid}-{page}.html"


def extract_body_text(html: str) -> str:
    m = re.search(r'id="postmessage_\d+"[^>]*>([\s\S]*?)</td>', html, re.I)
    body = m.group(1) if m else html
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"<[^>]+>", "", body)
    return body


async def main() -> None:
    sm = SessionManager()
    await sm.bootstrap(force=True)
    fetcher = Fetcher(sm)
    out: list = []

    try:
        await _run(fetcher, out)
    finally:
        await sm.close()

    path = Path(__file__).resolve().parents[1] / "data" / "structure_sample.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}")
    # compact console summary (ASCII-safe)
    for block in out:
        err = block.get("error")
        samples = block.get("samples") or []
        print(
            f"fid={block.get('fid')} n={block.get('list_count')} "
            f"samples={len(samples)} err={err or '-'}"
        )
        for s in samples[:2]:
            print(
                f"  tid={s.get('tid')} magnets={s.get('magnets')} ed2k={s.get('ed2k')} "
                f"tags={s.get('body_tags')[:8]} meta={s.get('meta_keys')}"
            )


async def _run(fetcher: Fetcher, out: list) -> None:
    for fid, preferred in SAMPLES:
        pol = BOARD_POLICIES[fid]
        list_url = board_list_url(fid)
        fetcher.set_referer(f"{BASE_URL}forum.php")
        try:
            list_html = await fetcher.get_list_html(list_url)
        except Exception as exc:  # noqa: BLE001
            out.append({"fid": fid, "name": pol.name, "error": f"list:{exc}"})
            continue

        threads = parse_forum_list(list_html, skip_sticky=True)
        tids = [t.tid for t in threads[:8]]
        if not tids:
            tids = [int(x) for x in re.findall(r"thread-(\d+)-", list_html)[:8]]

        samples = []
        for tid in tids[:3]:
            thread_url = f"{BASE_URL}thread-{tid}-1-1.html"
            fetcher.set_referer(list_url)
            try:
                thread_html = await fetcher.get_thread_html(thread_url)
            except Exception as exc:  # noqa: BLE001
                samples.append({"tid": tid, "error": str(exc)})
                continue

            content = parse_thread_content(thread_html, tid=tid)
            dual = parse_thread_dual(thread_html, tid=tid, preferred_link=preferred)
            body_text = extract_body_text(thread_html)
            body_tags = TAG_RE.findall(body_text[:5000])
            samples.append(
                {
                    "tid": tid,
                    "title": (content.title or "")[:100],
                    "meta_keys": list(content.metadata.keys()),
                    "password": bool(content.extract_password or dual.extract_password),
                    "magnets": len(dual.magnets),
                    "ed2k": len(dual.ed2k_links),
                    "primary": dual.primary_link_kind,
                    "body_tags": body_tags[:24],
                    "snippet": re.sub(r"\s+", " ", body_text[:260]).strip(),
                }
            )

        out.append(
            {
                "fid": fid,
                "name": pol.name,
                "category": pol.category,
                "primary_link": pol.primary_link,
                "hot": pol.hot,
                "list_typeid": pol.list_typeid,
                "list_url": list_url,
                "list_count": len(threads) or len(tids),
                "samples": samples,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
