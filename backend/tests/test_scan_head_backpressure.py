"""扫新帖：每板强制读列表；停止后不得续跑；收尾消化。"""

from __future__ import annotations

import asyncio


def test_scan_head_covers_all_boards_forced_list(monkeypatch):
    from crawler.throttle import THROTTLE
    from workers import runner

    THROTTLE.clear_stop()
    calls: list[dict] = []

    async def fake_crawl(**kwargs):
        calls.append(dict(kwargs))
        fid = str(kwargs.get("board_fid_override") or "")
        if not kwargs.get("scan_list"):
            return {
                "ok": True,
                "board_fid": fid or "95",
                "crawled": 0,
                "enqueued": 0,
                "discovered": 0,
                "imports": 0,
                "stubs": 0,
                "retries": 0,
                "failed": 0,
            }
        return {
            "ok": True,
            "board_fid": fid,
            "board_name": fid,
            "pages_head": [1],
            "enqueued": 3,
            "discovered": 3,
            "crawled": 3,
            "imports": 3,
            "stubs": 0,
            "retries": 0,
            "failed": 0,
            "head_completed": True,
        }

    monkeypatch.setattr(runner, "run_crawl_once", fake_crawl)
    monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda _cfg: ["95", "36", "141"])
    monkeypatch.setattr(runner, "resolve_manual_head_pages", lambda _cfg, _fid: 20)
    monkeypatch.setattr(runner, "load_forum_configs_map", lambda _conn: {"site": {}})
    monkeypatch.setattr(runner, "connect", lambda: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(runner, "_log_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_queue_schema", lambda: None)
    monkeypatch.setattr(runner, "SITE_CRAWLER_FORUM_ID", "site")
    monkeypatch.setattr(runner, "_STATE", {"running": False, "looping": False, "loop_inner": False, "phase": "idle", "activity": [], "throttle": {}, "queue": {}})

    out = asyncio.get_event_loop().run_until_complete(runner.run_scan_head_once(forum_id="site"))
    assert out.get("ok") is True
    boards = out.get("boards") or []
    assert [b["board_fid"] for b in boards] == ["95", "36", "141"]
    list_calls = [c for c in calls if c.get("scan_list")]
    assert len(list_calls) == 3
    assert all(c.get("force_list_scan") is True for c in list_calls)
    assert all(c.get("clear_stop_flag") is False for c in list_calls)
    assert all(c.get("hold_lock") is True for c in list_calls)


def test_scan_head_stops_skips_remaining_boards(monkeypatch):
    from crawler.throttle import THROTTLE
    from workers import runner

    THROTTLE.clear_stop()
    calls: list[dict] = []

    async def fake_crawl(**kwargs):
        calls.append(dict(kwargs))
        THROTTLE.request_stop()
        return {
            "ok": True,
            "board_fid": "95",
            "board_name": "A",
            "reason": "stopped",
            "pages_head": [1],
            "enqueued": 1,
            "discovered": 1,
            "crawled": 1,
            "imports": 0,
            "stubs": 0,
            "retries": 0,
            "failed": 0,
        }

    monkeypatch.setattr(runner, "run_crawl_once", fake_crawl)
    monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda _cfg: ["95", "36"])
    monkeypatch.setattr(runner, "resolve_manual_head_pages", lambda _cfg, _fid: 10)
    monkeypatch.setattr(runner, "load_forum_configs_map", lambda _conn: {"site": {}})
    monkeypatch.setattr(runner, "connect", lambda: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(runner, "_log_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_queue_schema", lambda: None)
    monkeypatch.setattr(runner, "SITE_CRAWLER_FORUM_ID", "site")
    monkeypatch.setattr(runner, "_STATE", {"running": False, "looping": False, "loop_inner": False, "phase": "idle", "activity": [], "throttle": {}, "queue": {}})

    out = asyncio.get_event_loop().run_until_complete(runner.run_scan_head_once(forum_id="site"))
    assert out.get("reason") == "stopped"
    assert len([c for c in calls if c.get("scan_list")]) == 1
    assert not any(str(c.get("board_fid_override")) == "36" and c.get("scan_list") for c in calls)
    assert THROTTLE.should_stop() is True
    THROTTLE.clear_stop()


def test_scan_head_drains_queue_after_lists(monkeypatch):
    from crawler.throttle import THROTTLE
    from workers import runner

    THROTTLE.clear_stop()
    calls: list[dict] = []
    ready_left = {"n": 5}

    async def fake_crawl(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("scan_list"):
            return {
                "ok": True,
                "board_fid": kwargs.get("board_fid_override"),
                "pages_head": [1],
                "enqueued": 5,
                "discovered": 5,
                "crawled": 2,
                "imports": 2,
                "stubs": 0,
                "retries": 0,
                "failed": 0,
                "head_completed": True,
            }
        # drain
        ready_left["n"] = max(0, ready_left["n"] - 3)
        return {
            "ok": True,
            "board_fid": "95",
            "crawled": 3,
            "enqueued": 0,
            "discovered": 0,
            "imports": 3,
            "stubs": 0,
            "retries": 0,
            "failed": 0,
        }

    monkeypatch.setattr(runner, "run_crawl_once", fake_crawl)
    monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda _cfg: ["95"])
    monkeypatch.setattr(runner, "resolve_manual_head_pages", lambda _cfg, _fid: 10)
    monkeypatch.setattr(runner, "load_forum_configs_map", lambda _conn: {"site": {}})
    monkeypatch.setattr(runner, "connect", lambda: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(runner, "_log_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_queue_schema", lambda: None)
    monkeypatch.setattr(runner, "SITE_CRAWLER_FORUM_ID", "site")
    monkeypatch.setattr(runner, "_STATE", {"running": False, "looping": False, "loop_inner": False, "phase": "idle", "activity": [], "throttle": {}, "queue": {}})
    monkeypatch.setattr(
        runner,
        "count_pending",
        lambda *_a, **_k: {"ready": ready_left["n"], "abnormal": 0, "workable": ready_left["n"]},
    )
    monkeypatch.setattr(runner, "enabled_queue_board_keys", lambda x: list(x))

    out = asyncio.get_event_loop().run_until_complete(runner.run_scan_head_once(forum_id="site"))
    assert out.get("ok") is True
    assert int(out.get("drain_rounds") or 0) >= 1
    assert any(not c.get("scan_list") for c in calls)
