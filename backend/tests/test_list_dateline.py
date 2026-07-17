"""发帖时间序列表 URL + 龄期过滤 + 每日首页捕新 / 深扫策略。"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from crawler.list_urls import build_list_url, list_url_for_board, pages_to_scan
from parsers.list_dates import is_thread_old_enough, parse_discuz_list_datetime


def test_list_urls_always_dateline():
    u95 = list_url_for_board("95:716", 1)
    assert "orderby=dateline" in u95
    assert "typeid=716" in u95
    assert "heats" not in u95

    u36 = list_url_for_board("36:368", 2)
    assert "orderby=dateline" in u36
    assert "typeid=368" in u36
    assert "heats" not in u36

    u = build_list_url("https://www.sehuatang.net/", 2, 1, hot=True)
    assert "heats" not in u
    assert "orderby=dateline" in u


def test_pages_start_at_one():
    assert pages_to_scan(pages_per_board=3, min_thread_age_days=3) == [1, 2, 3]
    assert pages_to_scan(pages_per_board=3, last_list_page=10) == [10, 11, 12]


def test_counted_resume_includes_end_page():
    from workers.list_scan import counted_resume_page

    assert counted_resume_page(5) == 5
    assert counted_resume_page(0) == 2
    assert counted_resume_page(1) == 2


def test_age_retry_after():
    from workers.list_scan import age_retry_after

    posted = datetime(2026, 7, 10, 15, 30)
    assert age_retry_after(posted, 3) == datetime(2026, 7, 13, 0, 0, 0)
    assert age_retry_after(None, 3) is None
    assert age_retry_after(posted, 0) is None


def test_age_filter():
    now = datetime(2026, 7, 14, 12, 0, 0)
    old = now - timedelta(days=5)
    fresh = now - timedelta(days=1)
    assert is_thread_old_enough(old, min_age_days=3, now=now)
    assert not is_thread_old_enough(fresh, min_age_days=3, now=now)
    assert is_thread_old_enough(None, min_age_days=3, now=now)


def test_parse_list_datetime():
    now = datetime(2026, 7, 14, 15, 30, 0)
    assert parse_discuz_list_datetime("2026-07-01", now=now) == datetime(2026, 7, 1)
    assert parse_discuz_list_datetime("昨天 12:00", now=now) == datetime(2026, 7, 13, 12, 0)
    assert parse_discuz_list_datetime("刚刚", now=now) == now


def test_is_board_head_done_today():
    from db.forum_configs import crawl_today, is_board_head_done_today

    today = crawl_today()
    assert is_board_head_done_today({"board_head_catchup_on": {"36": today}}, 36)
    assert not is_board_head_done_today({"board_head_catchup_on": {"36": "2000-01-01"}}, 36)
    assert not is_board_head_done_today({}, 36)


@pytest.mark.asyncio
async def test_head_stops_when_page_all_known(monkeypatch):
    """首页：连续 2 页全已知则完成扫新帖（默认 early-stop）。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    pages_fetched: list[int] = []

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        pages_fetched.append(page)
        if page == 1:
            batch = [
                ThreadBrief(tid=1, title="a", url="https://www.sehuatang.net/thread-1-1-1.html"),
                ThreadBrief(tid=2, title="b", url="https://www.sehuatang.net/thread-2-1-1.html"),
            ]
            return ls._PageFetch(ok=True, batch=batch)
        if page in (2, 3):
            batch = [
                ThreadBrief(tid=10 + page, title="c", url=f"https://www.sehuatang.net/thread-{10 + page}-1-1.html"),
            ]
            return ls._PageFetch(ok=True, batch=batch)
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(tid=99, title="x", url="https://www.sehuatang.net/thread-99-1-1.html"),
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        # tid>=12 视为已入库
        if any(t.tid >= 12 for t in batch):
            return 0, 0
        n = len(batch)
        out.enqueued += n
        for t in batch:
            out.threads.append(t)
        return n, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    fetcher = MagicMock()
    result = await ls.scan_board_list(
        fetcher,
        board_fid=36,
        pages_per_board=2,
        head_pages=50,
        known_stop_pages=2,
        scan_head=True,
        last_list_page=0,
        persist_enqueue=False,
    )
    assert result.pages_head == [1, 2, 3]
    assert result.head_completed is True
    assert 4 not in result.pages_head
    assert result.harvest_start_page == 4


@pytest.mark.asyncio
async def test_head_stops_after_one_known_when_configured(monkeypatch):
    """known_stop_pages=1：单页全已知即可结束扫新帖。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        if page == 1:
            batch = [
                ThreadBrief(tid=1, title="a", url="https://www.sehuatang.net/thread-1-1-1.html"),
                ThreadBrief(tid=2, title="b", url="https://www.sehuatang.net/thread-2-1-1.html"),
            ]
            return ls._PageFetch(ok=True, batch=batch)
        if page == 2:
            batch = [
                ThreadBrief(tid=3, title="c", url="https://www.sehuatang.net/thread-3-1-1.html"),
            ]
            return ls._PageFetch(ok=True, batch=batch)
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(tid=99, title="x", url="https://www.sehuatang.net/thread-99-1-1.html"),
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        if any(t.tid == 3 for t in batch):
            return 0, 0
        n = len(batch)
        out.enqueued += n
        for t in batch:
            out.threads.append(t)
        return n, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=2,
        head_pages=50,
        known_stop_pages=1,
        scan_head=True,
        last_list_page=0,
        persist_enqueue=False,
    )
    assert result.pages_head == [1, 2]
    assert result.head_completed is True
    assert 3 not in result.pages_head
    assert result.harvest_start_page == 3

@pytest.mark.asyncio
async def test_skip_head_continues_deep_until_repeat(monkeypatch):
    """跳过首页；本轮配额够时可持续到连续两页 tid 相同则到底。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    pages_fetched: list[int] = []

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        pages_fetched.append(page)
        # P30..P33 各页不同；P34 起与上一页相同 → 到底
        tid = 1000 + min(page, 33)
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(
                    tid=tid,
                    title=f"p{page}",
                    url=f"https://www.sehuatang.net/thread-{tid}-1-1.html",
                )
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        return 0, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=5,
        max_list_pages=0,
        scan_head=False,
        known_stop_pages=1,
        last_list_page=30,
        persist_enqueue=False,
    )
    assert result.head_skipped is True
    assert result.pages_head == []
    assert 1 not in pages_fetched
    assert result.pages_scanned == [30, 31, 32, 33]
    assert result.list_exhausted is True
    assert result.last_list_page == 33


@pytest.mark.asyncio
async def test_deep_respects_configured_page_cap(monkeypatch):
    """pages_per_board 始终作为本轮配额（即使 max_list_pages=0）。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(
                    tid=1000 + page,
                    title=f"p{page}",
                    url=f"https://www.sehuatang.net/thread-{1000 + page}-1-1.html",
                )
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        return 0, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=3,
        max_list_pages=0,
        scan_head=False,
        known_stop_pages=1,
        last_list_page=10,
        persist_enqueue=False,
    )
    assert result.pages_scanned == [10, 11, 12]
    assert result.last_list_page == 12
    assert result.list_exhausted is False
    assert result.deep_early_stop is False


@pytest.mark.asyncio
async def test_deep_stops_when_clamped_to_page1(monkeypatch):
    """超页夹回第 1 页内容时判定到底。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        if page == 1:
            batch = [
                ThreadBrief(tid=9, title="home", url="https://www.sehuatang.net/thread-9-1-1.html"),
            ]
        elif page <= 3:
            batch = [
                ThreadBrief(
                    tid=100 + page,
                    title=f"p{page}",
                    url=f"https://www.sehuatang.net/thread-{100 + page}-1-1.html",
                )
            ]
        else:
            # 夹回首页
            batch = [
                ThreadBrief(tid=9, title="home", url="https://www.sehuatang.net/thread-9-1-1.html"),
            ]
        return ls._PageFetch(ok=True, batch=batch)

    def fake_enqueue(out, batch, **kwargs):
        n = len(batch)
        out.enqueued += n
        return n, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=95,
        pages_per_board=50,
        max_list_pages=0,
        scan_head=True,
        head_pages=1,
        last_list_page=0,
        persist_enqueue=False,
    )
    assert 1 in result.pages_head
    assert result.list_exhausted is True
    assert result.last_list_page == 3
    assert result.pages_scanned == [2, 3]


@pytest.mark.asyncio
async def test_head_only_deep_scan_false(monkeypatch):
    """手动扫新帖：deep_scan=False 时不出现 pages_scanned。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    pages_fetched: list[int] = []

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        pages_fetched.append(page)
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(
                    tid=10 + page,
                    title=f"p{page}",
                    url=f"https://www.sehuatang.net/thread-{10 + page}-1-1.html",
                )
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        # P2/P3 整页已知 → 连续 2 页后捕新完成
        if all(t.tid >= 12 for t in batch):
            return 0, 0
        n = len(batch)
        out.enqueued += n
        for t in batch:
            out.threads.append(t)
        return n, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=50,
        max_list_pages=0,
        head_pages=20,
        known_stop_pages=2,
        scan_head=True,
        deep_scan=False,
        last_list_page=40,
        persist_enqueue=False,
    )
    assert result.pages_head == [1, 2, 3]
    assert result.head_completed is True
    assert result.pages_scanned == []
    assert 4 not in pages_fetched
    assert 40 not in pages_fetched


@pytest.mark.asyncio
async def test_deep_only_scan_head_false(monkeypatch):
    """自动深扫：scan_head=False 时不出现 pages_head。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    pages_fetched: list[int] = []

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        pages_fetched.append(page)
        return ls._PageFetch(
            ok=True,
            batch=[
                ThreadBrief(
                    tid=500 + page,
                    title=f"p{page}",
                    url=f"https://www.sehuatang.net/thread-{500 + page}-1-1.html",
                )
            ],
        )

    def fake_enqueue(out, batch, **kwargs):
        return 1, 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=2,
        max_list_pages=100,
        scan_head=False,
        deep_scan=True,
        last_list_page=20,
        persist_enqueue=False,
    )
    assert result.head_skipped is True
    assert result.pages_head == []
    assert 1 not in pages_fetched
    assert result.pages_scanned == [20, 21]


def test_resolve_manual_head_pages():
    from db.forum_configs import resolve_manual_head_pages

    assert resolve_manual_head_pages({}, 95) == 20
    assert resolve_manual_head_pages({"web_crawler_manual_head_pages": 15}, 95) == 15
    assert (
        resolve_manual_head_pages(
            {
                "web_crawler_manual_head_pages": 15,
                "board_manual_head_pages": {"95": 30, "2": 10},
            },
            95,
        )
        == 30
    )
    assert (
        resolve_manual_head_pages(
            {
                "web_crawler_manual_head_pages": 15,
                "board_manual_head_pages": {"95": 30},
            },
            2,
        )
        == 15
    )


def test_resolve_page_cap_always_uses_pages_per_board():
    from crawler.list_urls import resolve_page_cap

    assert resolve_page_cap(15, 0) == 15
    assert resolve_page_cap(15, 100) == 15
    assert resolve_page_cap(15, 10) == 10
    assert resolve_page_cap(0, 0) == 1


def test_board_141_skips_young_posts(monkeypatch):
    """板 141：未满 3 天帖跳过、不入队；满龄帖正常入队。"""
    from datetime import datetime, timedelta

    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    now = datetime(2026, 7, 15, 12, 0, 0)
    young = ThreadBrief(
        tid=1,
        title="young",
        url="https://www.sehuatang.net/thread-1-1-1.html",
        posted_at=now - timedelta(days=1),
    )
    aged = ThreadBrief(
        tid=2,
        title="aged",
        url="https://www.sehuatang.net/thread-2-1-1.html",
        posted_at=now - timedelta(days=4),
    )

    class _C:
        def close(self):
            return None

    enqueued_urls: list[str] = []

    def fake_enqueue_thread(conn, *, url, board_fid, board_name, title, retry_after=None):
        enqueued_urls.append(url)
        assert retry_after is None
        return True

    monkeypatch.setattr(ls, "connect", lambda: _C())
    monkeypatch.setattr(ls, "enqueue_thread", fake_enqueue_thread)
    monkeypatch.setattr(
        ls,
        "is_thread_old_enough",
        lambda posted_at, min_age_days=0: (now - posted_at).days >= min_age_days,
    )

    out = ls.ListScanResult(board_fid=141)
    enq, skipped = ls._enqueue_batch(
        out,
        [young, aged],
        seen=set(),
        board_fid=141,
        board_name="网友原创",
        persist_enqueue=True,
        min_thread_age_days=3,
    )
    assert enq == 1
    assert skipped == 1
    assert out.deferred_young == 1
    assert enqueued_urls == ["https://www.sehuatang.net/thread-2-1-1.html"]
    assert [t.tid for t in out.threads] == [2]
