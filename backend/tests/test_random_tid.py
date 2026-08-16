"""随机抓帖：tid 抽样、缺失页识别、批量早停、持久化/自适应。"""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.random_probes import estimate_tid_range
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


def test_sample_tids_weighted_respects_exclude():
    windows = [(1, 10, 0.5), (1, 10, 0.5)]
    out = rt.sample_tids_weighted(windows, 5, exclude={2, 4, 6}, rng=random.Random(3))
    assert len(out) == 5
    assert len(set(out)) == 5
    assert not ({2, 4, 6} & set(out))
    assert all(1 <= t <= 10 for t in out)


def test_estimate_tid_range_fallback_when_few_samples():
    plan = estimate_tid_range([100, 200], cfg_lo=80_000, cfg_hi=500_000)
    assert plan["adaptive"] is False
    assert plan["lo"] == 80_000
    assert plan["hi"] == 500_000
    assert plan["windows"] == [(80_000, 500_000, 1.0)]


def test_estimate_tid_range_adaptive_windows():
    # 均匀分布在 100k–200k，应收窄并开自适应
    tids = list(range(100_000, 200_001, 2_000))  # 51 个
    plan = estimate_tid_range(tids, cfg_lo=80_000, cfg_hi=500_000, min_samples=30)
    assert plan["adaptive"] is True
    assert plan["p10"] is not None and plan["p90"] is not None
    assert plan["lo"] >= 80_000
    assert plan["hi"] <= 500_000
    assert plan["lo"] < plan["hi"]
    assert len(plan["windows"]) >= 2
    # 全局探索窗仍覆盖配置硬边界
    spans = [(a, b) for a, b, _ in plan["windows"]]
    assert any(a == 80_000 and b == 500_000 for a, b in spans)


def test_is_missing_thread():
    assert rt.is_missing_thread("<html>抱歉，指定的主题不存在</html>", "提示信息") is True
    assert rt.is_missing_thread("<html><div id='postmessage_1'>正文</div></html>", "正常标题") is False
    # 空提示页不再当成永久不存在（限流常见）
    short = "<html><title>提示信息 - 论坛</title><body>ok</body></html>"
    assert rt.is_missing_thread(short, "提示信息 - 论坛") is False


def test_extract_board_fid():
    html = '<a href="forum.php?mod=forumdisplay&amp;fid=103">板块</a>'
    assert rt.extract_board_fid(html) == 103
    assert rt.extract_board_fid('<a href="/forum-36-1.html">x</a>') == 36
    assert rt.extract_board_fid("") is None


def _patch_batch_common(monkeypatch, *, fetcher, sample_ids: list[int]):
    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rt, "_persist_probe", lambda **k: True)
    monkeypatch.setattr(rt, "_load_exclude_tids", lambda forum_id="": (set(), 0, 0))
    monkeypatch.setattr(
        rt,
        "_resolve_sampling_plan",
        lambda **k: {
            "lo": k.get("cfg_lo", 1000),
            "hi": k.get("cfg_hi", 2000),
            "adaptive": False,
            "sample_n": 0,
            "windows": [(k.get("cfg_lo", 1000), k.get("cfg_hi", 2000), 1.0)],
        },
    )
    monkeypatch.setattr(rt.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rt.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rt.THROTTLE, "sleep", AsyncMock())
    monkeypatch.setattr(rt.THROTTLE, "record_success", lambda: None)

    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    session.bootstrap = AsyncMock()
    monkeypatch.setattr(rt, "session_from_config", lambda cfg, **k: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg, **k: fetcher)
    monkeypatch.setattr(rt, "is_tid_known", lambda conn, tid, url, **k: False)
    monkeypatch.setattr(
        rt,
        "sample_tids_weighted",
        lambda windows, n, exclude=None, rng=None: list(sample_ids[:n]),
    )

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())
    # run_random_tid_batch 总会读全局代理设置
    import db.settings_store as settings_store

    monkeypatch.setattr(settings_store, "get_setting", lambda conn, key, default="": default)
    return session


@pytest.mark.asyncio
async def test_random_batch_stops_at_import_target(monkeypatch):
    """入库+占位达目标即停，不必跑满 probe。"""
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(
        return_value='<html><title>资源帖</title><div id="postmessage_1">'
        '<a href="forum.php?fid=36">板</a>magnet:?xt=urn:btih:AABBCCDDEEFF00112233445566778899AABBCCDD'
        "</div></html>"
    )
    _patch_batch_common(monkeypatch, fetcher=fetcher, sample_ids=list(range(1000, 1020)))
    monkeypatch.setattr(rt, "is_missing_thread", lambda html, title="": False)
    monkeypatch.setattr(rt, "extract_board_fid", lambda html: 36)

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

    result = await rt.run_random_tid_batch(
        crawler_config={
            "web_crawl_urls": "https://www.sehuatang.net/forum.php",
            "web_crawler_random_tid_probe": 20,
            "web_crawler_random_tid_import_target": 3,
            "web_crawler_random_tid_min": 1000,
            "web_crawler_random_tid_max": 2000,
            "web_crawler_random_adaptive": "0",
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
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(
        return_value='<html><title>资源帖</title><div id="postmessage_1">'
        '<a href="forum.php?fid=36">板</a>magnet:?xt=urn:btih:AABBCCDDEEFF00112233445566778899AABBCCDD'
        "</div></html>"
    )
    _patch_batch_common(monkeypatch, fetcher=fetcher, sample_ids=list(range(1000, 1010)))
    monkeypatch.setattr(rt, "is_missing_thread", lambda html, title="": False)
    monkeypatch.setattr(rt, "extract_board_fid", lambda html: 36)

    async def fake_process(*args, **kwargs):
        return {
            "tid": kwargs.get("tid") or args[0],
            "verdict": "import",
            "outcome": "成功",
            "title": "t",
            "thread_url": "https://www.sehuatang.net/thread-1-1-1.html",
        }

    monkeypatch.setattr(rt, "process_thread", fake_process)

    rt.clear_random_session_state()
    rt._STATE["looping"] = True
    try:
        result = await rt.run_random_tid_batch(
            crawler_config={
                "web_crawl_urls": "https://www.sehuatang.net/forum.php",
                "web_crawler_random_adaptive": "0",
            },
            probe=5,
            import_target=0,
            persist=True,
            from_loop=True,
        )
        assert result["ok"] is True
        assert result["probed"] == 5
        assert result["imported"] == 5
        assert 1000 in rt._session_probed
        rt.clear_random_session_state()
        assert not rt._session_probed
    finally:
        rt._STATE["looping"] = False

    result2 = await rt.run_random_tid_batch(
        crawler_config={
            "web_crawl_urls": "https://www.sehuatang.net/forum.php",
            "web_crawler_random_adaptive": "0",
        },
        probe=3,
        import_target=0,
        persist=True,
        from_loop=False,
    )
    assert result2["ok"] is True
    assert not rt._session_probed


@pytest.mark.asyncio
async def test_random_batch_counts_missing(monkeypatch):
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(return_value="<html>主题不存在</html>")
    _patch_batch_common(monkeypatch, fetcher=fetcher, sample_ids=[11, 12, 13])
    process = AsyncMock()
    monkeypatch.setattr(rt, "process_thread", process)

    persisted: list[dict] = []

    def _capture_persist(**k):
        persisted.append(k)
        return True

    monkeypatch.setattr(rt, "_persist_probe", _capture_persist)

    result = await rt.run_random_tid_batch(
        crawler_config={
            "web_crawl_urls": "https://www.sehuatang.net/forum.php",
            "web_crawler_random_adaptive": "0",
        },
        probe=3,
        import_target=5,
        persist=False,
    )
    assert result["missing"] == 3
    assert result["imported"] == 0
    process.assert_not_called()
    assert len(persisted) == 3
    assert all(p.get("outcome") == "missing" for p in persisted)


@pytest.mark.asyncio
async def test_random_batch_excludes_persisted_probes(monkeypatch):
    """库内已探 + 已入库 tid 不得再进本轮抽样。"""
    fetcher = MagicMock()
    fetcher.get_thread_html = AsyncMock(return_value="<html>主题不存在</html>")
    seen_exclude: list[set[int]] = []

    def fake_weighted(windows, n, exclude=None, rng=None):
        seen_exclude.append(set(exclude or ()))
        return [101, 102]

    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rt, "_persist_probe", lambda **k: True)
    monkeypatch.setattr(rt, "_load_exclude_tids", lambda forum_id="": ({99, 100, 50}, 2, 1))
    monkeypatch.setattr(
        rt,
        "_resolve_sampling_plan",
        lambda **k: {
            "lo": 1,
            "hi": 200,
            "adaptive": False,
            "sample_n": 0,
            "windows": [(1, 200, 1.0)],
        },
    )
    monkeypatch.setattr(rt.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rt.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rt.THROTTLE, "sleep", AsyncMock())
    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    monkeypatch.setattr(rt, "session_from_config", lambda cfg, **k: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg, **k: fetcher)
    monkeypatch.setattr(rt, "is_tid_known", lambda conn, tid, url, **k: False)
    monkeypatch.setattr(rt, "sample_tids_weighted", fake_weighted)
    monkeypatch.setattr(rt, "process_thread", AsyncMock())

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())
    import db.settings_store as settings_store

    monkeypatch.setattr(settings_store, "get_setting", lambda conn, key, default="": default)
    rt.clear_random_session_state()

    result = await rt.run_random_tid_batch(
        crawler_config={
            "web_crawl_urls": "https://www.sehuatang.net/forum.php",
            "web_crawler_random_adaptive": "0",
        },
        probe=2,
        import_target=0,
        persist=False,
        from_loop=True,
    )
    assert result["persist_probed"] == 2
    assert result["exclude_known"] == 1
    assert seen_exclude and {99, 100, 50}.issubset(seen_exclude[0])
    rt.clear_random_session_state()


@pytest.mark.asyncio
async def test_random_batch_aborts_when_exclude_load_fails(monkeypatch):
    """排除集加载失败则中止，绝不空排除硬探。"""
    fetcher = MagicMock()
    monkeypatch.setattr(rt, "try_begin_exclusive", lambda phase="random_tid": {"ok": True})
    monkeypatch.setattr(rt, "end_exclusive", lambda: None)
    monkeypatch.setattr(rt, "_log_activity", lambda msg: None)

    def _boom(forum_id=""):
        raise RuntimeError("db down")

    monkeypatch.setattr(rt, "_load_exclude_tids", _boom)
    sampled = {"n": 0}

    def fake_weighted(windows, n, exclude=None, rng=None):
        sampled["n"] += 1
        return [1]

    monkeypatch.setattr(rt, "sample_tids_weighted", fake_weighted)
    session = MagicMock()
    session._ready = True
    session.close = AsyncMock()
    monkeypatch.setattr(rt, "session_from_config", lambda cfg, **k: session)
    monkeypatch.setattr(rt, "fetcher_from_config", lambda session, cfg, **k: fetcher)

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rt, "connect", lambda: _Conn())
    import db.settings_store as settings_store

    monkeypatch.setattr(settings_store, "get_setting", lambda conn, key, default="": default)

    result = await rt.run_random_tid_batch(
        crawler_config={"web_crawl_urls": "https://www.sehuatang.net/forum.php"},
        probe=3,
        import_target=0,
        persist=False,
    )
    assert result["ok"] is False
    assert result["reason"] == "load_exclude_failed"
    assert result["probed"] == 0
    assert sampled["n"] == 0


def test_load_known_tids_raises_on_crawl_pages_error():
    from db.random_probes import load_known_tids_for_exclude

    class _BadCur:
        def execute(self, *a, **k):
            raise RuntimeError("crawl_pages boom")

    class _BadConn:
        def cursor(self):
            return _BadCur()

    with pytest.raises(RuntimeError, match="crawl_pages boom"):
        load_known_tids_for_exclude(_BadConn(), None, forum_id="sehuatang")
