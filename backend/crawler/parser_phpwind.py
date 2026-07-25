"""PHPWind（人人为我 / 2048）列表与帖页解析。"""

from __future__ import annotations

import html as html_lib
import re
from urllib.parse import urljoin

from crawler.parser import ThreadBrief, ThreadDetail, Post, _clean_text

_TID_HREF_RE = re.compile(
    r'href=["\']([^"\']*read\.php\?[^"\']*?\btid=(\d+)[^"\']*)["\']',
    re.I,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def is_valid_phpwind_list(html: str) -> bool:
    if not html or len(html) < 800:
        return False
    if "var safeid" in html and len(html) < 12000:
        return False
    return "read.php?tid=" in html or "thread.php?fid=" in html


def parse_forum_list_phpwind(
    html: str,
    base_url: str = "https://fby.tfzqs88.com",
    skip_sticky: bool = False,
) -> list[ThreadBrief]:
    """从 PHPWind 板块列表抽取帖子。"""
    del skip_sticky  # PHPWind 列表置顶标记不稳定，暂不筛
    base = base_url if base_url.endswith("/") else base_url + "/"
    out: list[ThreadBrief] = []
    seen: set[int] = set()

    # DOM 优先
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "lxml")
        for a in soup.select("a[href*='read.php'][href*='tid=']"):
            href = a.get("href") or ""
            m = re.search(r"[?&]tid=(\d+)", href, re.I)
            if not m:
                continue
            tid = int(m.group(1))
            if tid in seen:
                continue
            title = a.get_text(" ", strip=True)
            title = html_lib.unescape(title)
            if not title or len(title) < 2:
                continue
            if title in ("上一主题", "下一主题", "新窗", "首页", "尾页"):
                continue
            seen.add(tid)
            url = urljoin(base, href.replace("&amp;", "&").split("#")[0])
            out.append(ThreadBrief(tid=tid, title=title, url=url))
    except Exception:
        out = []

    if out:
        return out

    # regex 回退
    for m in _TID_HREF_RE.finditer(html or ""):
        href = (m.group(1) or "").replace("&amp;", "&")
        tid = int(m.group(2))
        if tid in seen:
            continue
        # 粗取锚文本：href 后到 </a>
        tail = (html or "")[m.end() : m.end() + 400]
        tm = re.search(r">([^<]{2,120})</a>", tail, re.I)
        title = html_lib.unescape((tm.group(1) if tm else "").strip())
        if not title:
            continue
        seen.add(tid)
        out.append(
            ThreadBrief(
                tid=tid,
                title=title,
                url=urljoin(base, href.split("#")[0]),
            )
        )
    return out


def extract_phpwind_post_html(html: str) -> str:
    """取出楼主正文 HTML（#read_tpc / .tpc_content）。"""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        node = soup.select_one("#read_tpc") or soup.select_one(".tpc_content") or soup.select_one("#tpc")
        if node:
            return str(node)
    except Exception:
        pass
    m = re.search(
        r'<div[^>]+id=["\']read_tpc["\'][^>]*>(.*?)</div>\s*(?:</td>|</div>)',
        html,
        re.I | re.S,
    )
    if m:
        return m.group(0)
    return html


def parse_thread_phpwind(html: str, *, tid: int = 0) -> ThreadDetail:
    title = ""
    tm = _TITLE_RE.search(html or "")
    if tm:
        title = _clean_text(tm.group(1))
        # 去掉站名后缀
        if " - " in title:
            title = title.rsplit(" - ", 1)[0].strip()

    post_html = extract_phpwind_post_html(html)
    content = _clean_text(post_html) if post_html else _clean_text(html or "")
    posts = [Post(pid="tpc", floor=1, author="", content=content)]
    return ThreadDetail(tid=int(tid or 0), title=title, posts=posts)
