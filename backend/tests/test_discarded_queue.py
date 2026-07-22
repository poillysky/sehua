"""Discarded queue list helpers (failed / skipped)."""

from db.queue import (
    DISCARDED_STATUSES,
    _discarded_search_clause,
    _discarded_status_clause,
    count_discarded,
)


def test_discarded_status_clause_all():
    sql, params = _discarded_status_clause("all")
    assert "ANY" in sql
    assert params[0] == list(DISCARDED_STATUSES)


def test_discarded_status_clause_failed():
    sql, params = _discarded_status_clause("failed")
    assert "status = %s" in sql
    assert params == ["failed"]


def test_discarded_search_tid():
    sql, params = _discarded_search_clause("2254351")
    assert "tid = %s" in sql
    assert params[0] == 2254351


def test_discarded_search_empty():
    sql, params = _discarded_search_clause("  ")
    assert sql == ""
    assert params == []


def test_count_discarded_shape_without_db():
    """保证 count_discarded 返回结构稳定（mock cursor）。"""

    class FakeCur:
        def __init__(self):
            self._n = 0

        def execute(self, *_a, **_k):
            self._n += 1

        def fetchone(self):
            # failed=2, skipped=5
            return (2 if self._n == 1 else 5,)

    class FakeConn:
        def cursor(self):
            return FakeCur()

    out = count_discarded(FakeConn(), status="all")
    assert out["failed"] == 2
    assert out["skipped"] == 5
    assert out["total"] == 7


def test_discarded_kind_clause_patterns():
    from db.queue import _discarded_kind_outcome_clause

    sql, params = _discarded_kind_outcome_clause("access_denied_bad_title")
    assert "ILIKE" in sql
    assert any("无阅读权限" in p for p in params)


def test_failed_all_kind_clause_is_unrestricted():
    from db.queue import ACCOUNT_DISCARDED_KINDS, _discarded_kind_outcome_clause

    sql, params = _discarded_kind_outcome_clause("failed_all")
    assert sql == "TRUE"
    assert params == []
    assert ACCOUNT_DISCARDED_KINDS == ("failed_all", "access_denied_bad_title")


def test_unknown_discarded_kind_raises():
    from db.queue import count_discarded_kind

    class FakeConn:
        def cursor(self):
            raise AssertionError("should not query")

    try:
        count_discarded_kind(FakeConn(), "no_such_kind")
        assert False, "expected KeyError"
    except KeyError:
        pass
