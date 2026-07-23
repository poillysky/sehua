"""Postgres 拒收 NUL 的防护。"""

from __future__ import annotations

from parsers.safe_text import strip_nul, strip_nul_list


def test_strip_nul_removes_null_bytes():
    assert strip_nul("ab\x00c") == "abc"
    assert strip_nul(None) == ""
    assert strip_nul("ok") == "ok"
    assert strip_nul_list(["a\x00", "\x00", "b"]) == ["a", "b"]


def test_upsert_resource_strips_nul(monkeypatch):
    from parsers.ed2k import Ed2kLink
    from db import repository as repo

    calls: list[tuple] = []

    class _Cur:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            calls.append((sql, params))

        def fetchone(self):
            return (1,)

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            return None

    monkeypatch.setattr(repo, "_ensure_resource_schema", lambda conn: None)
    link = Ed2kLink(
        filename="f\x00ile",
        size=1,
        hash="a" * 32,
        link="ed2k://|file|x|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/",
    )
    repo.upsert_resource(
        _Conn(),
        link,
        source_id=1,
        source_url="https://example.com/t",
        title="t\x00itle",
        description="desc\x00",
        ed2k_links=["ed2k://|file|x|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/"],
        import_outcome="ok\x00",
        commit=False,
    )
    # first INSERT into ed2k_resources
    params = calls[0][1]
    assert "\x00" not in str(params)
    assert params[1] == "file"
