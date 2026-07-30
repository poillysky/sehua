# -*- coding: utf-8 -*-
"""同 tid 镜像去重：删除重复行，不写 duplicate_tid_url。"""

from __future__ import annotations

from db.queue import dedupe_pending_by_tid, enqueue_thread


class _FakeCur:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn
        self.rowcount = 0
        self._last = None

    def execute(self, sql: str, params=None) -> None:
        s = " ".join((sql or "").split())
        self._last = (s, params)
        self.conn.calls.append((s, params))
        # SELECT 1 … tid 已存在
        if s.startswith("SELECT 1 FROM crawl_pages") and self.conn.known_tid:
            self._fetch = [(1,)]
            self.rowcount = 1
            return
        if s.startswith("SELECT 1 FROM crawl_pages"):
            self._fetch = []
            self.rowcount = 0
            return
        if "DELETE FROM crawl_pages AS cp USING ranked" in s or (
            "DELETE FROM crawl_pages" in s and "duplicate_tid_url" in s
        ):
            self.rowcount = self.conn.delete_n
            return
        if s.startswith("INSERT INTO crawl_pages"):
            self.rowcount = 0 if self.conn.block_insert else 1
            return
        self.rowcount = 0
        self._fetch = []

    def fetchone(self):
        rows = getattr(self, "_fetch", [])
        return rows[0] if rows else None


class _FakeConn:
    def __init__(self) -> None:
        self.calls: list = []
        self.commits = 0
        self.known_tid = False
        self.block_insert = False
        self.delete_n = 2

    def cursor(self):
        return _FakeCur(self)

    def commit(self) -> None:
        self.commits += 1


def test_dedupe_pending_deletes_not_label_duplicate_tid_url():
    conn = _FakeConn()
    n = dedupe_pending_by_tid(conn, board_fid="3")
    assert n == 4  # pending dup delete_n + legacy delete_n
    assert conn.commits == 1
    joined = "\n".join(s for s, _ in conn.calls)
    assert "DELETE FROM crawl_pages" in joined
    assert "duplicate_tid_url" in joined
    assert "status = 'skipped'" not in joined
    assert "UPDATE crawl_pages AS cp SET status" not in joined


def test_enqueue_skips_when_same_tid_already_queued():
    conn = _FakeConn()
    conn.known_tid = True
    ok = enqueue_thread(
        conn,
        url="https://bbs.other.com/read.php?tid=24687403",
        board_fid=3,
        forum_id="2048",
        title="x",
    )
    assert ok is False
    assert not any(s.startswith("INSERT INTO crawl_pages") for s, _ in conn.calls)
