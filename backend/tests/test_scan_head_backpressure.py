"""扫新帖：全板强制读列表只入队；一次进站复用会话；再收尾消化。"""

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
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "retries": 0,
            "failed": 0,
            "head_completed": True,
            "crawl_threads": False,
        }

    monkeypatch.setattr(runner, "run_crawl_once", fake_crawl)
    monkeypatch.setattr(
        runner,
        "resolve_enabled_board_fids",
        lambda _cfg, forum_id=None: [
            "95:716",
            "141:689",
            "141:690",
            "36:368",
            "36:369",
        ],
    )
    monkeypatch.setattr(runner, "resolve_manual_head_pages", lambda _cfg, _fid: 20)
    monkeypatch.setattr(runner, "load_forum_configs_map", lambda _conn: {"site": {}})
    monkeypatch.setattr(runner, "connect", lambda: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(runner, "_log_activity", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "_ensure_queue_schema", lambda: None)
    monkeypatch.setattr(runner, "SITE_CRAWLER_FORUM_ID", "site")
    monkeypatch.setattr(runner, "_STATE", {"running": False, "looping": False, "loop_inner": False, "phase": "idle", "activity": [], "throttle": {}, "queue": {}})

    out = asyncio.get_event_loop().run_until_complete(runner.run_scan_head_once(forum_id="site"))
    assert out.get("ok") is True
    assert out.get("scan_board_fids") == ["95:716", "141", "36"]
    boards = out.get("boards") or []
    assert [b["board_fid"] for b in boards] == ["95:716", "141", "36"]
    list_calls = [c for c in calls if c.get("scan_list")]
    assert [str(c.get("board_fid_override")) for c in list_calls] == ["95:716", "141", "36"]
    assert len(list_calls) == 3
    assert all(c.get("force_list_scan") is True for c in list_calls)
    assert all(c.get("clear_stop_flag") is False for c in list_calls)
    assert all(c.get("hold_lock") is True for c in list_calls)
    assert all(c.get("crawl_threads") is False for c in list_calls)
    assert all(c.get("from_loop") is True for c in list_calls)


def test_collapse_to_parent_board_fids():
    from parsers.boards import collapse_to_parent_board_fids, is_parent_of_enabled

    assert collapse_to_parent_board_fids(
        ["95:716", "141:689", "141:690", "36", "36:368"]
    ) == ["95", "141", "36"]
    from parsers.boards import scan_head_board_keys

    assert scan_head_board_keys(
        ["95:716", "141:689", "141:690", "36:368", "36:369", "37"]
    ) == ["95:716", "141", "36", "37"]
    assert is_parent_of_enabled("141", ["141:689", "95:716"]) is True
    assert is_parent_of_enabled("999", ["141:689"]) is False



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
    monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda _cfg, forum_id=None: ["95", "36"])
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
    monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda _cfg, forum_id=None: ["95"])
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
    list_calls = [c for c in calls if c.get("scan_list")]
    drain_calls = [c for c in calls if not c.get("scan_list")]
    assert all(c.get("crawl_threads") is False for c in list_calls)
    assert all(c.get("crawl_threads") is True for c in drain_calls)
    assert all(c.get("from_loop") is True for c in calls)
