"""Parse forum index and section metadata."""

from __future__ import annotations

import html as html_lib
import re
from dataclasses import dataclass


@dataclass
class ForumSection:
    fid: int
    name: str
    url: str
    parent: str = ""


def parse_forum_index(html: str, base_url: str = "https://www.sehuatang.net/") -> list[ForumSection]:
    """Extract all forum sections from forum.php homepage."""
    sections: list[ForumSection] = []
    seen: set[int] = set()

    # forum-{fid}.html or forum.php?mod=forumdisplay&fid={fid}
    patterns = [
        re.compile(
            r'href="(?:https?://[^"]+/)?forum-(\d+)-1\.html"[^>]*>([^<]+)</a>',
            re.I,
        ),
        re.compile(
            r'href="(?:https?://[^"]+/)?forum\.php\?mod=forumdisplay&amp;fid=(\d+)"[^>]*>([^<]+)</a>',
            re.I,
        ),
        re.compile(
            r'href="forum-(\d+)-1\.html"[^>]*>([^<]+)</a>',
            re.I,
        ),
    ]

    current_group = ""
    for line in html.splitlines():
        group_m = re.search(r'class="gstitle"[^>]*>(?:<a[^>]*>)?([^<]+)', line, re.I)
        if group_m:
            current_group = html_lib.unescape(group_m.group(1)).strip()

        for pat in patterns:
            for m in pat.finditer(line):
                fid = int(m.group(1))
                if fid in seen:
                    continue
                name = html_lib.unescape(m.group(2)).strip()
                name = re.sub(r"\s+", " ", name)
                if not name or name in ("收藏本版", "发新帖"):
                    continue
                seen.add(fid)
                sections.append(
                    ForumSection(
                        fid=fid,
                        name=name,
                        url=f"{base_url}forum-{fid}-1.html",
                        parent=current_group,
                    )
                )

    # Whole-page fallback if line-by-line missed entries
    if len(sections) < 5:
        seen.clear()
        sections.clear()
        for pat in patterns:
            for m in pat.finditer(html):
                fid = int(m.group(1))
                if fid in seen:
                    continue
                name = html_lib.unescape(m.group(2)).strip()
                if not name:
                    continue
                seen.add(fid)
                sections.append(
                    ForumSection(
                        fid=fid,
                        name=name,
                        url=f"{base_url}forum-{fid}-1.html",
                    )
                )

    sections.sort(key=lambda s: s.fid)
    return sections


def find_forum_by_name(sections: list[ForumSection], keyword: str) -> list[ForumSection]:
    kw = keyword.strip()
    return [s for s in sections if kw in s.name]
