"""Discuz forum list and thread parsers."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass, field


@dataclass
class ThreadBrief:
    tid: int
    title: str
    author: str = ""
    url: str = ""
    is_sticky: bool = False
    posted_at: object | None = None  # datetime | None


@dataclass
class Post:
    pid: str
    floor: int
    author: str
    content: str


@dataclass
class ThreadDetail:
    tid: int
    title: str
    posts: list[Post] = field(default_factory=list)


def _clean_text(raw: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def parse_forum_list(
    html: str,
    base_url: str = "https://www.sehuatang.net/",
    skip_sticky: bool = False,
    *,
    min_thread_age_days: int = 0,
) -> list[ThreadBrief]:
    """Extract thread entries from a forum list page (发帖时间序列表)。

    Supports SEO links ``thread-{tid}-1-1.html`` and Discuz viewthread links.
    When ``min_thread_age_days`` > 0, drop rows younger than the cutoff
    (unknown dates kept).
    """
    from parsers.list_dates import is_thread_old_enough, parse_discuz_list_datetime

    base = base_url if base_url.endswith("/") else base_url + "/"
    threads = _parse_forum_list_dom(html, base=base, skip_sticky=skip_sticky)
    if not threads:
        threads = _parse_forum_list_regex(html, base=base, skip_sticky=skip_sticky)

    if min_thread_age_days > 0:
        threads = [
            t
            for t in threads
            if is_thread_old_enough(t.posted_at, min_age_days=min_thread_age_days)  # type: ignore[arg-type]
        ]
    return threads


def _parse_forum_list_dom(
    html: str,
    *,
    base: str,
    skip_sticky: bool,
) -> list[ThreadBrief]:
    from parsers.list_dates import parse_discuz_list_datetime

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html or "", "lxml")
    out: list[ThreadBrief] = []
    seen: set[int] = set()
    for tb in soup.select("tbody[id^=normalthread_], tbody[id^=stickthread_]"):
        tid_m = re.search(r"_(?P<tid>\d+)$", tb.get("id") or "")
        if not tid_m:
            continue
        tid = int(tid_m.group("tid"))
        is_sticky = (tb.get("id") or "").startswith("stickthread_")
        if skip_sticky and is_sticky:
            continue
        anchor = None
        for a in tb.select("a[href]"):
            href = a.get("href") or ""
            if "thread-" in href or "mod=viewthread" in href:
                anchor = a
                break
        if not anchor:
            continue
        title = anchor.get_text(strip=True)
        if not title or title in ("上一主题", "下一主题"):
            continue
        if tid in seen:
            continue
        seen.add(tid)
        posted_at = None
        by_cell = tb.select_one("td.by")
        if by_cell:
            em = by_cell.select_one("em span") or by_cell.select_one("em")
            if em:
                posted_at = parse_discuz_list_datetime(em.get_text(strip=True))
        out.append(
            ThreadBrief(
                tid=tid,
                title=html_lib.unescape(title),
                url=f"{base}thread-{tid}-1-1.html",
                is_sticky=is_sticky,
                posted_at=posted_at,
            )
        )
    return out


def _parse_forum_list_regex(
    html: str,
    *,
    base: str,
    skip_sticky: bool,
) -> list[ThreadBrief]:
    threads: list[ThreadBrief] = []
    seen: set[int] = set()
    sticky_tids: set[int] = set()
    for m in re.finditer(r'<tbody[^>]*\bid="(stickthread|normalthread)_(\d+)"', html, re.I):
        kind, tid_s = m.group(1).lower(), m.group(2)
        if kind == "stickthread":
            sticky_tids.add(int(tid_s))

    patterns = [
        re.compile(
            r'href="(?:https?://[^"]+/)?thread-(\d+)-1-\d+\.html"'
            r'[^>]*(?:title="([^"]*)")?[^>]*>([^<]+)</a>',
            re.I,
        ),
        re.compile(
            r'href="(?:(?:https?://[^"]+/)?(?:\./)?)?forum\.php\?mod=viewthread&amp;tid=(\d+)[^"]*"'
            r'[^>]*(?:title="([^"]*)")?[^>]*>([^<]+)</a>',
            re.I,
        ),
        re.compile(
            r'href="(?:(?:https?://[^"]+/)?(?:\./)?)?forum\.php\?mod=viewthread&tid=(\d+)[^"]*"'
            r'[^>]*(?:title="([^"]*)")?[^>]*>([^<]+)</a>',
            re.I,
        ),
    ]

    for pattern in patterns:
        for m in pattern.finditer(html):
            tid = int(m.group(1))
            if tid in seen:
                continue
            seen.add(tid)
            title = html_lib.unescape(m.group(2) or m.group(3)).strip()
            if not title or title in ("上一主题", "下一主题"):
                continue
            is_sticky = tid in sticky_tids
            if skip_sticky and is_sticky:
                continue
            threads.append(
                ThreadBrief(
                    tid=tid,
                    title=title,
                    url=f"{base}thread-{tid}-1-1.html",
                    is_sticky=is_sticky,
                )
            )

    if not threads:
        for m in re.finditer(r'<tbody[^>]*\bid="(stickthread|normalthread)_(\d+)"', html, re.I):
            kind, tid = m.group(1).lower(), int(m.group(2))
            is_sticky = kind == "stickthread"
            if skip_sticky and is_sticky:
                continue
            if tid in seen:
                continue
            seen.add(tid)
            threads.append(
                ThreadBrief(
                    tid=tid,
                    title=f"(tid={tid})",
                    url=f"{base}thread-{tid}-1-1.html",
                    is_sticky=is_sticky,
                )
            )
    return threads


def parse_thread(html: str, tid: int) -> ThreadDetail:
    """Extract thread title and posts from a thread detail page."""
    title = ""
    m = re.search(r'id="thread_subject"[^>]*>([^<]+)<', html)
    if m:
        title = html_lib.unescape(m.group(1)).strip()
    if not title:
        tm = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        if tm:
            title = _clean_text(tm.group(1)).split(" - ")[0].strip()

    posts: list[Post] = []

    # Discuz post blocks
    for block in re.finditer(
        r'id="post_(\d+)"[^>]*>.*?id="postmessage_(\d+)"[^>]*>(.*?)</td>',
        html,
        re.I | re.S,
    ):
        pid = block.group(2)
        raw_content = block.group(3)
        content = _clean_text(raw_content)
        if not content:
            continue

        # Author near this post block
        start = max(0, block.start() - 800)
        snippet = html[start : block.start()]
        author_m = re.search(r'class="xi2"[^>]*>([^<]+)</a>', snippet)
        author = html_lib.unescape(author_m.group(1)).strip() if author_m else ""

        posts.append(
            Post(
                pid=pid,
                floor=len(posts) + 1,
                author=author,
                content=content[:500],
            )
        )

    # Fallback: postmessage only
    if not posts:
        for i, pm in enumerate(
            re.finditer(r'id="postmessage_(\d+)"[^>]*>(.*?)</td>', html, re.I | re.S),
            start=1,
        ):
            content = _clean_text(pm.group(2))
            if content:
                posts.append(Post(pid=pm.group(1), floor=i, author="", content=content[:500]))

    return ThreadDetail(tid=tid, title=title, posts=posts)


def is_valid_forum_list(html: str) -> bool:
    return "Powered by Discuz" in html and ("thread-" in html or "forumdisplay" in html)


def is_valid_thread(html: str) -> bool:
    return "Powered by Discuz" in html and ("postmessage" in html or 'id="post_' in html)
