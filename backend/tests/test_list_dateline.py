"""发帖时间序列表 URL + 龄期过滤。"""

from __future__ import annotations

from datetime import datetime, timedelta

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

    # hot flag ignored
    u = build_list_url("https://www.sehuatang.net/", 2, 1, hot=True)
    assert "heats" not in u
    assert "orderby=dateline" in u


def test_pages_start_at_one():
    assert pages_to_scan(pages_per_board=3, min_thread_age_days=3) == [1, 2, 3]
    # 含结束页重读，避免漏帖：停在 10 → 从 10 开始
    assert pages_to_scan(pages_per_board=3, last_list_page=10) == [10, 11, 12]


def test_counted_resume_includes_end_page():
    from workers.list_scan import counted_resume_page

    assert counted_resume_page(5) == 5
    assert counted_resume_page(0) == 2
    assert counted_resume_page(1) == 2


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
