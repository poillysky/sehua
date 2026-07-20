"""账号 Cookie 爬优先占位：筛选范围与升级删 stub。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from db.repository import ACCOUNT_STUB_OUTCOMES
from workers import recrawl as rc


def test_priority_outcomes_include_login_perm_attach_exclude_reply_purchase():
    assert "帖子需论坛登录" in ACCOUNT_STUB_OUTCOMES
    assert "无阅读权限 · 占位入库" in ACCOUNT_STUB_OUTCOMES
    assert "无权限下载附件" in ACCOUNT_STUB_OUTCOMES
    assert "需回复贴" not in ACCOUNT_STUB_OUTCOMES
    assert "需购买贴" not in ACCOUNT_STUB_OUTCOMES
    assert ACCOUNT_STUB_OUTCOMES[0] == "帖子需论坛登录"
    assert ACCOUNT_STUB_OUTCOMES[1] == "无阅读权限 · 占位入库"
    assert ACCOUNT_STUB_OUTCOMES[2] == "无权限下载附件"


def test_list_priority_sql_filters_outcomes_and_stub_prefix(monkeypatch):
    """查询应限定 unavailable stub + 三类 outcome，并按优先级排序。"""
    captured: dict = {}

    class _Cur:
        description = [
            ("hash",),
            ("ed2k_link",),
            ("source_url",),
            ("import_outcome",),
            ("board_fid",),
            ("board_name",),
            ("title",),
            ("updated_at",),
        ]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchall(self):
            return []

    class _Conn:
        def cursor(self):
            return _Cur()

    from db import repository as repo

    monkeypatch.setattr(repo, "_ensure_resource_schema", lambda conn: None)
    repo.list_priority_account_stubs(_Conn(), limit=10)
    sql = captured["sql"]
    params = captured["params"]
    assert "import_outcome IN %s" in sql
    assert "LIKE %s" in sql
    assert params[0].startswith("unavailable://")
    assert params[1] == tuple(ACCOUNT_STUB_OUTCOMES)
    assert params[2:5] == tuple(ACCOUNT_STUB_OUTCOMES)
    assert params[5] == 10
    assert "WHEN rs.import_outcome = %s THEN 0" in sql


@pytest.mark.asyncio
async def test_recrawl_account_stubs_requires_cookie(monkeypatch):
    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(rc, "crawl_status", lambda: {"looping": False, "running": False})
    monkeypatch.setattr(rc, "connect", lambda: _Conn())
    monkeypatch.setattr(
        rc,
        "_load_crawler_cfg",
        lambda conn: {"web_crawler_account_cookie": ""},
    )
    monkeypatch.setattr(rc, "_publish_account_stub_progress", lambda **kw: None)

    result = await rc.recrawl_account_stubs()
    assert result["ok"] is False
    assert result["reason"] == "no_account_cookie"
    assert "账号 Cookie" in (result.get("error") or "")


@pytest.mark.asyncio
async def test_recrawl_account_stubs_upgrade_deletes_stub(monkeypatch):
    class _Conn:
        def close(self):
            return None

    deletes: list[str] = []
    calls = {"n": 0}

    monkeypatch.setattr(rc, "crawl_status", lambda: {"looping": False, "running": False})
    monkeypatch.setattr(rc, "connect", lambda: _Conn())
    monkeypatch.setattr(rc, "try_begin_exclusive", lambda phase="account_stubs": {"ok": True})
    monkeypatch.setattr(rc, "end_exclusive", lambda: None)
    monkeypatch.setattr(rc, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rc.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(rc.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rc.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rc, "_publish_account_stub_progress", lambda **kw: None)
    monkeypatch.setattr(rc, "_db_priority_remaining", lambda exclude_hashes=None: 0)
    monkeypatch.setattr(
        rc,
        "_load_crawler_cfg",
        lambda conn: {
            "web_crawler_account_cookie": "uid=1; auth=x",
            "active_board_fid": "36",
        },
    )
    monkeypatch.setattr(rc, "count_priority_account_stubs", lambda conn, exclude_hashes=None: 1)

    def fake_list(conn, limit=1, exclude_hashes=None):
        calls["n"] += 1
        if calls["n"] > 1:
            return []
        return [
            {
                "hash": "stubhash1",
                "source_url": "https://www.sehuatang.net/thread-12345-1-1.html",
                "import_outcome": "帖子需论坛登录",
                "board_fid": "36",
                "board_name": "测试板",
                "title": "测试标题",
            }
        ]

    monkeypatch.setattr(rc, "list_priority_account_stubs", fake_list)

    session = MagicMock()
    session.bootstrap = AsyncMock()
    session.close = AsyncMock()
    session_calls: list[dict] = []

    def fake_session(cfg, **kwargs):
        session_calls.append(kwargs)
        return session

    monkeypatch.setattr(rc, "session_from_config", fake_session)
    monkeypatch.setattr(rc, "fetcher_from_config", lambda session, cfg: MagicMock())

    async def fake_process(*args, **kwargs):
        assert kwargs.get("account_stub_pass") is True
        return {
            "verdict": "import",
            "outcome": "正常入库",
            "tid": args[0] if args else kwargs.get("tid"),
        }

    monkeypatch.setattr(rc, "process_thread", fake_process)
    monkeypatch.setattr(
        rc,
        "delete_stub_by_source_url",
        lambda conn, url: deletes.append(url) or True,
    )

    result = await rc.recrawl_account_stubs()
    assert result["ok"] is True
    assert result["upgraded"] == 1
    assert result["still_stub"] == 0
    assert result["failed"] == 0
    assert deletes == ["https://www.sehuatang.net/thread-12345-1-1.html"]
    assert session_calls and session_calls[0].get("cookie_override") == "uid=1; auth=x"
    assert session_calls[0].get("account_jar") is True
    assert result["items"][0].get("stub_removed") is True


@pytest.mark.asyncio
async def test_recrawl_account_stubs_keeps_stub_on_still_stub(monkeypatch):
    class _Conn:
        def close(self):
            return None

    deletes: list[str] = []
    calls = {"n": 0}

    monkeypatch.setattr(rc, "crawl_status", lambda: {"looping": False, "running": False})
    monkeypatch.setattr(rc, "connect", lambda: _Conn())
    monkeypatch.setattr(rc, "try_begin_exclusive", lambda phase="account_stubs": {"ok": True})
    monkeypatch.setattr(rc, "end_exclusive", lambda: None)
    monkeypatch.setattr(rc, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rc.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(rc.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rc.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rc, "_publish_account_stub_progress", lambda **kw: None)
    monkeypatch.setattr(rc, "_db_priority_remaining", lambda exclude_hashes=None: 1)
    monkeypatch.setattr(
        rc,
        "_load_crawler_cfg",
        lambda conn: {
            "web_crawler_account_cookie": "uid=1",
            "active_board_fid": "36",
        },
    )
    monkeypatch.setattr(rc, "count_priority_account_stubs", lambda conn, exclude_hashes=None: 1)

    def fake_list(conn, limit=1, exclude_hashes=None):
        calls["n"] += 1
        if calls["n"] > 1:
            return []
        return [
            {
                "hash": "stubhash2",
                "source_url": "https://www.sehuatang.net/thread-99-1-1.html",
                "import_outcome": "无权限下载附件",
                "board_fid": "36",
                "board_name": "板",
                "title": "t",
            }
        ]

    monkeypatch.setattr(rc, "list_priority_account_stubs", fake_list)
    session = MagicMock()
    session.bootstrap = AsyncMock()
    session.close = AsyncMock()
    monkeypatch.setattr(rc, "session_from_config", lambda cfg, **kw: session)
    monkeypatch.setattr(rc, "fetcher_from_config", lambda session, cfg: MagicMock())
    monkeypatch.setattr(
        rc,
        "process_thread",
        AsyncMock(return_value={"verdict": "stub", "outcome": "无权限下载附件"}),
    )
    monkeypatch.setattr(
        rc,
        "delete_stub_by_source_url",
        lambda conn, url: deletes.append(url) or True,
    )

    result = await rc.recrawl_account_stubs()
    assert result["ok"] is True
    assert result["still_stub"] == 1
    assert result["upgraded"] == 0
    assert deletes == []


@pytest.mark.asyncio
async def test_recrawl_account_stubs_skips_reply_required(monkeypatch):
    class _Conn:
        def close(self):
            return None

    deletes: list[str] = []
    calls = {"n": 0}

    monkeypatch.setattr(rc, "crawl_status", lambda: {"looping": False, "running": False})
    monkeypatch.setattr(rc, "connect", lambda: _Conn())
    monkeypatch.setattr(rc, "try_begin_exclusive", lambda phase="account_stubs": {"ok": True})
    monkeypatch.setattr(rc, "end_exclusive", lambda: None)
    monkeypatch.setattr(rc, "_log_activity", lambda msg: None)
    monkeypatch.setattr(rc.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(rc.THROTTLE, "clear_stop", lambda: None)
    monkeypatch.setattr(rc.THROTTLE, "should_stop", lambda: False)
    monkeypatch.setattr(rc, "_publish_account_stub_progress", lambda **kw: None)
    monkeypatch.setattr(rc, "_db_priority_remaining", lambda exclude_hashes=None: 0)
    monkeypatch.setattr(
        rc,
        "_load_crawler_cfg",
        lambda conn: {
            "web_crawler_account_cookie": "uid=1",
            "active_board_fid": "36",
        },
    )
    monkeypatch.setattr(rc, "count_priority_account_stubs", lambda conn, exclude_hashes=None: 1)

    def fake_list(conn, limit=1, exclude_hashes=None):
        calls["n"] += 1
        if calls["n"] > 1:
            return []
        return [
            {
                "hash": "stubhash3",
                "source_url": "https://www.sehuatang.net/thread-88-1-1.html",
                "import_outcome": "帖子需论坛登录",
                "board_fid": "36",
                "board_name": "板",
                "title": "reply",
            }
        ]

    monkeypatch.setattr(rc, "list_priority_account_stubs", fake_list)
    session = MagicMock()
    session.bootstrap = AsyncMock()
    session.close = AsyncMock()
    monkeypatch.setattr(rc, "session_from_config", lambda cfg, **kw: session)
    monkeypatch.setattr(rc, "fetcher_from_config", lambda session, cfg: MagicMock())
    monkeypatch.setattr(
        rc,
        "process_thread",
        AsyncMock(
            return_value={
                "verdict": "skipped",
                "outcome": "需回复贴（账号爬跳过）",
            }
        ),
    )
    monkeypatch.setattr(
        rc,
        "delete_stub_by_source_url",
        lambda conn, url: deletes.append(url) or True,
    )

    result = await rc.recrawl_account_stubs()
    assert result["ok"] is True
    assert result["skipped_prep"] == 1
    assert result["still_stub"] == 0
    assert result["upgraded"] == 0
    assert result["failed"] == 0
    assert deletes == ["https://www.sehuatang.net/thread-88-1-1.html"]
    assert result["items"][0].get("skipped") is True
