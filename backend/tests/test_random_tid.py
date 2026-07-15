"""随机抓帖：tid 抽样、缺失页识别、批量早停。"""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from workers import random_tid as rt


def test_sample_tids_unique_in_range():
    rng = random.Random(42)
    out = rt.sample_tids(100, 200, 10, rng=rng)
    assert len(out) == 10
    assert len(set(out)) == 10
    assert all(100 <= t <= 200 for t in out)


def test_sample_tids_respects_exclude_and_pool():
    out = rt.sample_tids(1, 5, 10, exclude={2, 4}, rng=random.Random(1))
    assert set(out) == {1, 3, 5}
    assert 2 not in out


def test_is_missing_thread():
    assert rt.is_missing_thread("<html>抱歉，指定的主题不存在</html>", "提示信息") is True
    assert rt.is_missing_thread("<html><div id='postmessage_1'>正文</div></html>", "正常标题") is False
    short = "<html><title>提示信息 - 论坛</title><body>ok</body></html>"
    assert rt.is_missing_thread(short, "提示信息 - 论坛") is True


def test_extract_board_fid():
    html = '<a href="forum.php?mod=forumdisplay&amp;fid=103">板块</a>'
    assert rt.extract_board_fid(html) == 103
    assert rt.extract_board_fid('<a href="/forum-36-1.html">x</a>') == 36
    assert rt.extract_board_fid("") is None


@pytest.mark.asyncio
async def test_random_batch_stops_at_import_target(monkeypatch):
    """入库+占位达目标即停，不必跑满 probe。"""
    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rt.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rt.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rt.THROTTLE, "sleep", AsyncMock())
    monkeypatch.setattr(rt.THROTTLE, "record_success", lambda: None)

    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    session.bootstrap = AsyncMock()
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(
        return_value='<html><title>资源帖</title><div id="postmessage_1">'
        '<a href="forum.php?fid=36">板</a>magnet:?xt=urn:btih:AABBCCDDEEFF00112233445566778899AABBCCDD'
        "</div></html>"
    )
    monkeypatch.setattr(rt, "session_from_config", lambda cfg: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg: fetcher)
    monkeypatch.setattr(rt, "is_tid_known", lambda conn, tid, url: False)
    monkeypatch.setattr(rt, "is_missing_thread", lambda html, title="": False)
    monkeypatch.setattr(rt, "extract_board_fid", lambda html: 36)

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())

    calls = {"n": 0}

    async def fake_process(*args, **kwargs):
        calls["n"] += 1
        return {
            "tid": kwargs.get("tid") or args[0],
            "verdict": "import",
            "outcome": "成功",
            "title": "t",
            "thread_url": "https://www.sehuatang.net/thread-1-1-1.html",
        }

    monkeypatch.setattr(rt, "process_thread", fake_process)
    monkeypatch.setattr(
        rt,
        "sample_tids",
        lambda lo, hi, n, exclude=None, rng=None: list(range(1000, 1000 + n)),
    )

    # avoid real DB for config load
    result = await rt.run_random_tid_batch(
        crawler_config={
            "web_crawl_urls": "https://www.sehuatang.net/forum.php",
            "web_crawler_random_tid_probe": 20,
            "web_crawler_random_tid_import_target": 3,
            "web_crawler_random_tid_min": 1000,
            "web_crawler_random_tid_max": 2000,
        },
        probe=20,
        import_target=3,
        persist=True,
    )
    assert result["ok"] is True
    assert result["imported"] == 3
    assert result["probed"] == 3
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_random_batch_runs_full_probe_when_target_zero(monkeypatch):
    """import_target=0：不早停，跑满 probe。"""
    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rt.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rt.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rt.THROTTLE, "sleep", AsyncMock())
    monkeypatch.setattr(rt.THROTTLE, "record_success", lambda: None)

    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    session.bootstrap = AsyncMock()
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(
        return_value='<html><title>资源帖</title><div id="postmessage_1">'
        '<a href="forum.php?fid=36">板</a>magnet:?xt=urn:btih:AABBCCDDEEFF00112233445566778899AABBCCDD'
        "</div></html>"
    )
    monkeypatch.setattr(rt, "session_from_config", lambda cfg: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg: fetcher)
    monkeypatch.setattr(rt, "is_tid_known", lambda conn, tid, url: False)
    monkeypatch.setattr(rt, "is_missing_thread", lambda html, title="": False)
    monkeypatch.setattr(rt, "extract_board_fid", lambda html: 36)

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())

    async def fake_process(*args, **kwargs):
        return {
            "tid": kwargs.get("tid") or args[0],
            "verdict": "import",
            "outcome": "成功",
            "title": "t",
            "thread_url": "https://www.sehuatang.net/thread-1-1-1.html",
        }

    monkeypatch.setattr(rt, "process_thread", fake_process)
    monkeypatch.setattr(
        rt,
        "sample_tids",
        lambda lo, hi, n, exclude=None, rng=None: list(range(1000, 1000 + n)),
    )

    rt.clear_random_session_state()
    rt._STATE["looping"] = True
    try:
        result = await rt.run_random_tid_batch(
            crawler_config={"web_crawl_urls": "https://www.sehuatang.net/forum.php"},
            probe=5,
            import_target=0,
            persist=True,
            from_loop=True,
        )
        assert result["ok"] is True
        assert result["probed"] == 5
        assert result["imported"] == 5
        # 循环中会话保留已抽 tid；停止时才清空
        assert 1000 in rt._session_probed
        rt.clear_random_session_state()
        assert not rt._session_probed
    finally:
        rt._STATE["looping"] = False

    # 单次任务结束即清空会话
    result2 = await rt.run_random_tid_batch(
        crawler_config={"web_crawl_urls": "https://www.sehuatang.net/forum.php"},
        probe=3,
        import_target=0,
        persist=True,
        from_loop=False,
    )
    assert result2["ok"] is True
    assert not rt._session_probed


@pytest.mark.asyncio
async def test_random_batch_counts_missing(monkeypatch):
    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rt.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rt.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rt.THROTTLE, "sleep", AsyncMock())

    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    session.bootstrap = AsyncMock()
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(return_value="<html>主题不存在</html>")
    monkeypatch.setattr(rt, "session_from_config", lambda cfg: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg: fetcher)
    monkeypatch.setattr(rt, "is_tid_known", lambda conn, tid, url: False)
    monkeypatch.setattr(
        rt,
        "sample_tids",
        lambda lo, hi, n, exclude=None, rng=None: [11, 12, 13],
    )

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())
    process = AsyncMock()
    monkeypatch.setattr(rt, "process_thread", process)

    result = await rt.run_random_tid_batch(
        crawler_config={"web_crawl_urls": "https://www.sehuatang.net/forum.php"},
        probe=3,
        import_target=5,
        persist=False,
    )
    assert result["missing"] == 3
    assert result["imported"] == 0
    process.assert_not_called()
