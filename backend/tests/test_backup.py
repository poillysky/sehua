"""资源库单份滚动备份：覆盖写、失败保留旧文件、停爬虫后恢复。"""

from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from workers import backup as bk


@pytest.fixture(autouse=True)
def _isolate_backup_paths(tmp_path, monkeypatch):
    latest = tmp_path / "ed2k-resources.sql.gz"
    tmp = tmp_path / "ed2k-resources.sql.gz.tmp"
    monkeypatch.setattr(bk, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(bk, "BACKUP_PATH", latest)
    monkeypatch.setattr(bk, "BACKUP_TMP_PATH", tmp)
    if bk._LOCK.locked():
        bk._LOCK.release()
    bk._BUSY = False
    yield


def test_backup_file_info_missing():
    info = bk.backup_file_info()
    assert info["exists"] is False
    assert info["bytes"] == 0


@pytest.mark.asyncio
async def test_run_backup_replaces_latest(monkeypatch):
    old = bk.BACKUP_PATH
    old.write_bytes(b"old-content-xxxxxxxx")

    def fake_dump(tables, dest_tmp: Path):
        with gzip.open(dest_tmp, "wb", compresslevel=1) as gz:
            gz.write(b"-- dump ok " + b"x" * 64)

    monkeypatch.setattr(bk, "_run_pg_dump", fake_dump)
    monkeypatch.setattr(bk, "_existing_tables", lambda conn: ["ed2k_resources"])
    monkeypatch.setattr(bk, "_write_last_status", lambda **kw: None)
    monkeypatch.setattr(
        bk,
        "_crawler_snapshot",
        lambda: {"was_enabled": False, "was_looping": False, "loop_kind": None},
    )
    monkeypatch.setattr(bk, "_pause_crawler", AsyncMock())
    monkeypatch.setattr(bk, "_resume_crawler", AsyncMock())

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bk, "connect", lambda: _Conn())

    result = await bk.run_backup_once(trigger="manual")
    assert result["ok"] is True
    assert bk.BACKUP_PATH.is_file()
    assert not bk.BACKUP_TMP_PATH.exists()
    data = gzip.open(bk.BACKUP_PATH, "rb").read()
    assert data.startswith(b"-- dump ok")
    assert b"old-content" not in data


@pytest.mark.asyncio
async def test_run_backup_keeps_old_on_failure(monkeypatch):
    bk.BACKUP_PATH.write_bytes(b"keep-me-please-xxxxxxxxxx")

    def boom(tables, dest_tmp):
        raise RuntimeError("pg_dump down")

    monkeypatch.setattr(bk, "_run_pg_dump", boom)
    monkeypatch.setattr(bk, "_existing_tables", lambda conn: ["ed2k_resources"])
    monkeypatch.setattr(bk, "_write_last_status", lambda **kw: None)
    snap = {"was_enabled": True, "was_looping": True, "loop_kind": "deep"}
    monkeypatch.setattr(bk, "_crawler_snapshot", lambda: snap)
    monkeypatch.setattr(bk, "_pause_crawler", AsyncMock())
    resume = AsyncMock()
    monkeypatch.setattr(bk, "_resume_crawler", resume)

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bk, "connect", lambda: _Conn())

    result = await bk.run_backup_once(trigger="manual")
    assert result["ok"] is False
    assert "pg_dump" in (result.get("error") or "")
    assert bk.BACKUP_PATH.read_bytes() == b"keep-me-please-xxxxxxxxxx"
    resume.assert_awaited_once()
    assert resume.await_args.args[0]["was_enabled"] is True
    assert resume.await_args.kwargs.get("ok") is False


@pytest.mark.asyncio
async def test_pause_and_resume_when_enabled(monkeypatch):
    import workers.runner as runner

    stop = AsyncMock()
    start_loop = MagicMock(return_value={"ok": True})
    monkeypatch.setattr(runner, "stop_crawler", stop)
    monkeypatch.setattr(
        runner,
        "crawl_status",
        lambda: {"running": True, "looping": True, "loop_kind": "deep"},
    )
    monkeypatch.setattr(runner, "start_continuous_loop", start_loop)
    monkeypatch.setattr(runner, "_log_activity", lambda msg: None)
    monkeypatch.setattr(bk, "_wait_crawler_idle", AsyncMock(return_value=True))

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bk, "connect", lambda: _Conn())
    monkeypatch.setattr(
        bk,
        "load_forum_configs_map",
        lambda conn: {bk.SITE_CRAWLER_FORUM_ID: {"web_crawler_enabled": True}},
    )
    monkeypatch.setattr(bk, "save_forum_config", lambda conn, fid, cfg: None)

    snap = {
        "was_enabled": True,
        "was_looping": True,
        "loop_kind": "deep",
    }
    await bk._pause_crawler(snap)
    stop.assert_awaited()

    await bk._resume_crawler(snap, ok=True)
    start_loop.assert_called_once()


def test_save_backup_config_clamps(monkeypatch):
    stored: dict[str, str] = {}

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(bk, "connect", lambda: _Conn())
    monkeypatch.setattr(bk, "set_setting", lambda conn, k, v: stored.__setitem__(k, v))
    monkeypatch.setattr(
        bk,
        "get_setting",
        lambda conn, k, default="": stored.get(k, default),
    )
    monkeypatch.setattr(bk, "backup_file_info", lambda: {"exists": False, "bytes": 0, "filename": "x"})
    monkeypatch.setattr(bk, "is_backup_busy", lambda: False)

    cfg = bk.save_backup_config(enabled=True, hour=99, minute=-3)
    assert stored[bk.SETTING_ENABLED] == "true"
    assert stored[bk.SETTING_HOUR] == "23"
    assert stored[bk.SETTING_MINUTE] == "0"
    assert cfg["hour"] == 23
    assert cfg["minute"] == 0
    assert cfg["enabled"] is True
