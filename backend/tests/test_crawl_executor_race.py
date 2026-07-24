"""crawl_executor must accept submit only after the loop is actually running."""

from __future__ import annotations

import asyncio
import time

from workers import crawl_executor as ce


def test_submit_right_after_construct_does_not_race() -> None:
    # Force a fresh executor so we hit the startup race window.
    with ce._executor_lock:
        ce._executor = None

    async def _ping() -> str:
        await asyncio.sleep(0)
        return "ok"

    # Burst: construct + submit must not raise「爬虫事件循环未就绪」
    for _ in range(20):
        with ce._executor_lock:
            ce._executor = None
        fut = ce.spawn_crawl(_ping(), name="race-probe")
        assert fut.result(timeout=5) == "ok"

    # Still running after burst
    assert ce.get_crawl_executor().loop.is_running()
    # tiny settle so daemon thread isn't mid-tear in other tests
    time.sleep(0.05)
