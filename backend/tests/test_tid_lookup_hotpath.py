"""Hot-path queries must use indexed equality, not leading-wildcard LIKE."""

from __future__ import annotations

from db.queue import canonical_thread_url
from db.repository import STUB_LINK_PREFIX, _priority_stub_where, known_resource_tids


class _Cur:
    def __init__(self, store: list) -> None:
        self._store = store
        self._rows: list = []

    def __enter__(self) -> "_Cur":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self._store.append((sql, params))

    def fetchall(self) -> list:
        return self._rows


class _Conn:
    def __init__(self, rows: list | None = None) -> None:
        self.calls: list = []
        self._rows = rows or []
        self.committed = False

    def cursor(self) -> _Cur:
        cur = _Cur(self.calls)
        cur._rows = self._rows
        return cur

    def commit(self) -> None:
        self.committed = True


def test_known_resource_tids_uses_exact_urls(monkeypatch) -> None:
    monkeypatch.setattr("db.repository._ensure_resource_schema", lambda _conn: None)
    urls = [
        canonical_thread_url("https://www.sehuatang.net/thread-1-1-1.html"),
        canonical_thread_url("https://www.sehuatang.net/thread-2-1-1.html"),
    ]
    conn = _Conn(rows=[(urls[0],)])
    got = known_resource_tids(conn, [1, 2])  # type: ignore[arg-type]
    assert got == {1}
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "LIKE" not in sql.upper()
    assert "source_url = ANY(%s)" in sql
    assert params == (urls,)


def test_priority_stub_where_no_lower_wrap() -> None:
    where, params = _priority_stub_where()
    assert "lower(" not in where.lower()
    assert "COALESCE(r.ed2k_link" not in where
    assert "r.ed2k_link LIKE %s" in where
    assert params[0] == f"{STUB_LINK_PREFIX}%"
