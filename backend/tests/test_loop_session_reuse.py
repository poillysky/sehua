"""连续调度：仅必要时进站，跨轮复用会话。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_loop_session_reuse_skips_bootstrap(monkeypatch):
    import workers.runner as runner

    async def _run() -> None:
        await runner.release_loop_session()
        runner.THROTTLE.clear_stop()

        boots: list[dict] = []

        class FakeSession:
            def __init__(self) -> None:
                self._ready = False
                self._page = None
                self.active_entry_url = ""
                self.cookies = {"safe": "1"}

            async def bootstrap(self, force: bool = False, **kwargs):
                boots.append({"force": force, **kwargs})
                self._ready = True
                self._page = object()
                self.active_entry_url = "https://www.sehuatang.net/"
                return self.cookies

            async def close(self):
                self._ready = False
                self._page = None

        fake = FakeSession()
        activities: list[str] = []

        monkeypatch.setattr(runner, "_log_activity", lambda m: activities.append(str(m)))
        monkeypatch.setattr(runner, "session_from_config", lambda *a, **k: fake)
        monkeypatch.setattr(
            runner, "fetcher_from_config", lambda *a, **k: SimpleNamespace(set_referer=lambda *_: None)
        )
        monkeypatch.setattr(
            runner,
            "resolve_forum_entry_urls",
            lambda *a, **k: ["https://www.sehuatang.net/"],
        )
        monkeypatch.setattr(runner, "bootstrap_probe_for_forum", lambda *a, **k: "")
        monkeypatch.setattr(runner, "connect", MagicMock())
        monkeypatch.setattr(runner, "get_setting", lambda *a, **k: "")
        monkeypatch.setattr(
            runner,
            "load_forum_configs_map",
            lambda *_: {
                "sehuatang": {
                    "web_crawler_enabled": True,
                    "active_board_fid": "95",
                    "web_crawler_request_delay": 0.1,
                    "web_crawler_autothrottle_window": 20,
                    "web_crawler_autothrottle_max_delay": 60,
                }
            },
        )
        monkeypatch.setattr(runner, "get_active_forum_id", lambda *_: "sehuatang")
        monkeypatch.setattr(runner, "resolve_enabled_board_fids", lambda *a, **k: ["95"])
        monkeypatch.setattr(runner, "queue_board_keys", lambda *a, **k: ["95"])
        monkeypatch.setattr(runner, "enabled_queue_board_keys", lambda *a, **k: ["95"])
        monkeypatch.setattr(runner, "count_pending", lambda *a, **k: {"ready": 0, "abnormal": 0})
        monkeypatch.setattr(runner, "fetch_pending_threads", lambda *a, **k: [])
        monkeypatch.setattr(runner, "fetch_pending_abnormal", lambda *a, **k: [])
        monkeypatch.setattr(runner, "_ensure_queue_schema", lambda: None)

        pol = SimpleNamespace(
            fid=95,
            list_typeid=0,
            name="板",
            primary_link="ed2k",
            min_thread_age_days=0,
        )
        adapter = SimpleNamespace(
            board_policies=lambda: {"95": pol},
            get_board_policy=lambda key: pol,
            build_list_url=lambda *a, **k: "https://www.sehuatang.net/forum-95-1.html",
        )
        monkeypatch.setattr(runner, "get_site_adapter", lambda *_: adapter)

        r1 = await runner.run_crawl_once(
            forum_id="sehuatang",
            persist=False,
            scan_list=False,
            from_loop=True,
            require_enabled=False,
        )
        assert r1.get("ok") is True, r1
        assert len(boots) == 1
        assert any("进站就绪" in a for a in activities)
        assert runner._loop_session is fake

        activities.clear()
        r2 = await runner.run_crawl_once(
            forum_id="sehuatang",
            persist=False,
            scan_list=False,
            from_loop=True,
            require_enabled=False,
        )
        assert r2.get("ok") is True, r2
        assert len(boots) == 1
        assert any("复用进站会话" in a for a in activities)

        runner.invalidate_loop_session(reason="test")
        activities.clear()
        r3 = await runner.run_crawl_once(
            forum_id="sehuatang",
            persist=False,
            scan_list=False,
            from_loop=True,
            require_enabled=False,
        )
        assert r3.get("ok") is True, r3
        assert len(boots) == 2
        assert boots[-1]["force"] is True
        assert any("进站中" in a for a in activities)

        await runner.release_loop_session()
        assert runner._loop_session is None

    asyncio.run(_run())
