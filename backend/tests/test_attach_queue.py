"""附件日限队列：命中日限入队、当日直入队、排水停于日限。"""

from __future__ import annotations

from parsers.attachments import (
    AttachmentFetchResult,
    is_attachment_denied,
    is_attachment_download_limited,
)
from workers.attach_queue import (
    ATTACH_QUEUE_FORUM_ID,
    ATTACH_QUEUE_OUTCOME,
    ATTACH_QUEUE_STATUS,
    ATTACH_QUEUE_VERDICT,
    forum_uses_attach_daily_queue,
    is_attach_daily_limit_hit,
    mark_attach_daily_limit_hit,
)


def test_daily_limit_tip_markers():
    tip = "今天下载 txt 已达 <b>50</b> 个，请明天再来。"
    assert is_attachment_download_limited(tip) is True
    assert is_attachment_denied(tip) is True


def test_attachment_fetch_result_has_daily_limited_flag():
    r = AttachmentFetchResult(denied=True, daily_limited=True)
    assert r.daily_limited is True
    assert r.denied is True
    r2 = AttachmentFetchResult()
    assert r2.daily_limited is False


def test_attach_queue_only_for_2048():
    assert forum_uses_attach_daily_queue("2048") is True
    assert forum_uses_attach_daily_queue(ATTACH_QUEUE_FORUM_ID) is True
    assert forum_uses_attach_daily_queue("sehuatang") is False
    assert forum_uses_attach_daily_queue("") is False
    assert forum_uses_attach_daily_queue(None) is False


def test_mark_and_detect_daily_limit_hit(monkeypatch):
    store: dict[str, str] = {}

    class _FakeConn:
        def commit(self):
            return None

        def close(self):
            return None

    def fake_connect():
        return _FakeConn()

    def fake_get(_conn, key, default=""):
        return store.get(key, default)

    def fake_set(_conn, key, value):
        store[key] = value

    monkeypatch.setattr("workers.attach_queue.connect", fake_connect)
    monkeypatch.setattr("workers.attach_queue.get_setting", fake_get)
    monkeypatch.setattr("workers.attach_queue.set_setting", fake_set)

    assert is_attach_daily_limit_hit("2048", today="2026-07-28") is False
    mark_attach_daily_limit_hit("2048", today="2026-07-28")
    assert is_attach_daily_limit_hit("2048", today="2026-07-28") is True
    assert is_attach_daily_limit_hit("2048", today="2026-07-29") is False
    # 非 2048：标记与查询均无效
    mark_attach_daily_limit_hit("sehuatang", today="2026-07-28")
    assert is_attach_daily_limit_hit("sehuatang", today="2026-07-28") is False
    assert store  # 2048 写入成功
    assert all("sehuatang" not in k for k in store)


def test_mark_thread_attach_queue_sql(monkeypatch):
    executed: list[tuple] = []

    class _Cur:
        def execute(self, sql, params=None):
            executed.append((sql, params))

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            return None

    from workers.attach_queue import mark_thread_attach_queue

    mark_thread_attach_queue(
        _Conn(),
        "https://bbs.sbnlfe.cn/read.php?tid=26888255",
        outcome=ATTACH_QUEUE_OUTCOME,
    )
    assert executed
    sql, params = executed[0]
    assert "UPDATE crawl_pages" in sql
    assert params[0] == ATTACH_QUEUE_STATUS
    assert ATTACH_QUEUE_OUTCOME in str(params[1])
    assert params[2] == "attachment_daily_limit"


def test_attach_queue_constants():
    assert ATTACH_QUEUE_VERDICT == "attach_queued"
    assert ATTACH_QUEUE_FORUM_ID == "2048"
    assert "附件日限" in ATTACH_QUEUE_OUTCOME
