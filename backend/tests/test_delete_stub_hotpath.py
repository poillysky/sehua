"""delete_stub_by_source_url must not seq-scan ed2k_resources."""

from __future__ import annotations

from db.repository import STUB_LINK_PREFIX, delete_stub_by_source_url, thread_stub_hash


class _Cur:
    def __init__(self, store: list) -> None:
        self._store = store

    def __enter__(self) -> "_Cur":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self._store.append((sql, params))

    def fetchall(self) -> list:
        return []


class _Conn:
    def __init__(self) -> None:
        self.calls: list = []

    def cursor(self) -> _Cur:
        return _Cur(self.calls)


def test_delete_stub_uses_pk_then_source_url(monkeypatch) -> None:
    deleted: list[str] = []
    monkeypatch.setattr(
        "db.repository.delete_resource_by_hash",
        lambda _conn, h: deleted.append(h) or True,
    )
    conn = _Conn()
    url = "https://www.sehuatang.net/thread-2663290-1-1.html"
    assert delete_stub_by_source_url(conn, url) is False
    assert len(conn.calls) == 2
    sql0, params0 = conn.calls[0]
    sql1, params1 = conn.calls[1]
    assert " OR " not in f" {sql0.upper()} "
    assert "lower(" not in sql0.lower()
    assert params0 == (thread_stub_hash(url), f"{STUB_LINK_PREFIX}%")
    assert "source_url = %s" in sql1
    assert params1 == (url, f"{STUB_LINK_PREFIX}%")
    assert deleted == []
