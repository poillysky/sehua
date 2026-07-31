# -*- coding: utf-8 -*-
"""不合格重爬：按 tid 直查 hash，不依赖明细分页硬顶。"""

from __future__ import annotations

import inspect

from db import repository as repo


def test_list_frame_fail_limit_cap_is_5000():
    src = inspect.getsource(repo.list_frame_fail_posts)
    assert "min(5000" in src
    assert "min(200," not in src


def test_resolve_frame_fail_hashes_by_tids_filters_like_false_friends(monkeypatch):
    """LIKE thread-3419820- 勿命中 34198200；每 tid 只取一条代表 hash。"""
    calls: list[int] = []

    class _Cur:
        def execute(self, sql, params=None):
            # params 末尾三个 LIKE 里含目标 tid
            self._tid = None
            for p in params or ():
                s = str(p)
                if s.startswith("%thread-") and s.endswith("-%"):
                    try:
                        self._tid = int(s[len("%thread-") : -2])
                    except ValueError:
                        self._tid = None

        def fetchall(self):
            tid = self._tid
            calls.append(int(tid or 0))
            rows = [
                (
                    "https://www.sehuatang.net/thread-3419820-1-1.html",
                    "4BE3D553D076AB2E66D9DA27B7DA0E88",
                ),
                (
                    "https://www.sehuatang.net/thread-34198200-1-1.html",
                    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                ),
            ]
            if tid == 3419820:
                return rows
            return []

        def fetchone(self):
            return (1,)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

    monkeypatch.setattr(repo, "_ensure_resource_schema", lambda _c: None)
    out = repo.resolve_frame_fail_hashes_by_tids(
        _Conn(), [3419820], forum_id="sehuatang"
    )
    assert calls == [3419820]
    assert len(out) == 1
    assert out[0]["tid"] == 3419820
    assert out[0]["hash"].startswith("4BE3")
