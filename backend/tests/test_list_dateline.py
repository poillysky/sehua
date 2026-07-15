"""发帖时间序列表 URL + 龄期过滤 + 每日首页捕新 / 深扫策略。"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from crawler.list_urls import build_list_url, list_url_for_board, pages_to_scan
from parsers.list_dates import is_thread_old_enough, parse_discuz_list_datetime


def test_list_urls_always_dateline():
    u95 = list_url_for_board(95, 1)
    assert "orderby=dateline" in u95
    assert "typeid=716" in u95
    assert "heats" not in u95

    u36 = list_url_for_board(36, 2)
    assert "orderby=dateline" in u36
    assert "filter=author" in u36 or "filter=typeid" in u36
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
    """首页：P1 有新帖扩到 P2，P2 全已知则完成捕新。"""
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
            return 0
        n = len(batch)
        out.enqueued += n
        for t in batch:
            out.threads.append(t)
        return n

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
    assert result.pages_head == [1, 2]
    assert result.head_completed is True
    assert 3 not in result.pages_head
    assert result.harvest_start_page == 3


@pytest.mark.asyncio
async def test_skip_head_when_done_today(monkeypatch):
    """今日已捕新：本轮不再读第 1 页，只深扫。"""
    from crawler.parser import ThreadBrief
    from workers import list_scan as ls

    pages_fetched: list[int] = []

    async def fake_fetch(fetcher, *, board_fid, page, root, pol):
        pages_fetched.append(page)
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
        return 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=10,
        scan_head=False,
        known_stop_pages=2,
        last_list_page=10,
        persist_enqueue=False,
    )
    assert result.head_skipped is True
    assert result.pages_head == []
    assert 1 not in pages_fetched
    assert result.pages_scanned == [10, 11]
    assert result.deep_early_stop is True


@pytest.mark.asyncio
async def test_deep_early_stop_on_known_streak(monkeypatch):
    """深扫连续 2 页全已知则早停。"""
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
        return 0

    monkeypatch.setattr(ls, "_fetch_list_page", fake_fetch)
    monkeypatch.setattr(ls, "_enqueue_batch", fake_enqueue)
    monkeypatch.setattr(ls.THROTTLE, "should_stop", lambda: False)

    async def _sleep():
        return None

    monkeypatch.setattr(ls.THROTTLE, "sleep", _sleep)

    result = await ls.scan_board_list(
        MagicMock(),
        board_fid=36,
        pages_per_board=10,
        scan_head=False,
        known_stop_pages=2,
        last_list_page=10,
        persist_enqueue=False,
    )
    assert result.deep_early_stop is True
    assert result.pages_scanned == [10, 11]
    assert result.last_list_page == 11
