# -*- coding: utf-8 -*-
"""AutoThrottle：默认延迟、成功降速、首帖减半。"""

from __future__ import annotations

import asyncio
import time

import pytest

from crawler.throttle import AutoThrottle


def test_configure_floor_and_default():
    t = AutoThrottle()
    t.configure(base_delay=0.1)
    assert t.base_delay == 0.3
    assert t.current_delay == 0.3
    assert t.min_delay() == 0.3


def test_success_can_drop_below_base():
    t = AutoThrottle()
    t.configure(base_delay=1.0)
    assert t.current_delay == 1.0
    for _ in range(12):
        t.record_success()
    assert t.current_delay <= 1.0
    assert t.current_delay >= t.min_delay()
    assert t.current_delay < 1.0  # 已降到 base 以下


def test_failure_raises_delay():
    t = AutoThrottle()
    t.configure(base_delay=1.0, max_delay=60.0, window=10)
    for _ in range(5):
        t.record_failure()
    assert t.current_delay > 1.0


@pytest.mark.asyncio
async def test_first_sleep_is_half():
    t = AutoThrottle()
    t.configure(base_delay=0.4)
    t.current_delay = 0.4
    t0 = time.perf_counter()
    await t.sleep()
    elapsed = time.perf_counter() - t0
    # 首帖约 0.2s，允许一点调度抖动
    assert 0.12 <= elapsed < 0.35
    t1 = time.perf_counter()
    await t.sleep()
    elapsed2 = time.perf_counter() - t1
    assert elapsed2 >= 0.35


@pytest.mark.asyncio
async def test_get_http_prefers_curl(monkeypatch):
    from crawler.fetcher import Fetcher
    from crawler.session import SessionManager

    calls: list[str] = []

    class FakeSession(SessionManager):
        def __init__(self) -> None:
            pass

        _ready = True
        cookies: dict = {}

        async def bootstrap(self, force: bool = False) -> None:
            return None

        def save(self) -> None:
            return None

    f = Fetcher(FakeSession(), timeout=10)  # type: ignore[arg-type]

    def fake_http(url: str) -> str:
        calls.append("curl")
        return "<html><body>thread</body></html>"

    async def fake_api(url: str) -> str:
        calls.append("browser")
        return "<html><body>thread</body></html>"

    monkeypatch.setattr(f, "_http_get", fake_http)
    monkeypatch.setattr(f, "_browser_api_get", fake_api)
    monkeypatch.setattr(f, "_is_cf_challenge", lambda html: False)
    monkeypatch.setattr(f, "_assert_usable_html", lambda *a, **k: None)
    monkeypatch.setattr(
        "crawler.session.SessionManager.is_safe_shell", staticmethod(lambda html: False)
    )

    html = await f._get_http("https://example.com/t/1")
    assert "thread" in html
    assert calls == ["curl"]
