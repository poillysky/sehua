"""upsert_resource 占用检查必须走 hash 等值，禁止 upper(hash)= 全表扫。"""

from __future__ import annotations

from parsers.ed2k import Ed2kLink


class _Cur:
    def __init__(self, store: list) -> None:
        self._store = store
        self._sql = ""

    def __enter__(self) -> "_Cur":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params=None) -> None:
        self._sql = sql
        self._store.append((sql, params))

    def fetchone(self):
        # 占用检查：假装未被占用
        if "FROM resource_sources" in (self._sql or "") and "WHERE hash" in (
            self._sql or ""
        ):
            return None
        if "RETURNING" in (self._sql or "").upper():
            return (1,)
        return None

    def fetchall(self) -> list:
        return []


class _Conn:
    def __init__(self) -> None:
        self.calls: list = []

    def cursor(self) -> _Cur:
        return _Cur(self.calls)

    def commit(self) -> None:
        return None


def test_upsert_ownership_check_uses_hash_equality(monkeypatch) -> None:
    monkeypatch.setattr("db.repository._ensure_resource_schema", lambda _c: None)
    from db.repository import upsert_resource

    conn = _Conn()
    link = Ed2kLink(
        filename="x",
        size=0,
        hash="abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd",
        link="magnet:?xt=urn:btih:abcdabcdabcdabcdabcdabcdabcdabcdabcdabcd",
    )
    upsert_resource(
        conn,
        link,
        source_id=1,
        source_url="https://www.sehuatang.net/thread-1-1-1.html",
        commit=True,
    )
    ownership = [
        sql
        for sql, _ in conn.calls
        if "FROM resource_sources" in sql and "source_url" in sql.lower()
    ]
    assert ownership, "expected ownership SELECT"
    sql = ownership[0]
    assert "upper(hash)" not in sql.lower()
    assert "WHERE hash = %s" in sql.replace("\n", " ")
    # 入参应已规范化为大写
    params = next(p for s, p in conn.calls if s is ownership[0])
    assert params[0] == "ABCDABCDABCDABCDABCDABCDABCDABCDABCDABCD"
