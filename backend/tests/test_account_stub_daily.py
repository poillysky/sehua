"""账号重爬每日额度。"""

from __future__ import annotations

from workers import account_stub_daily as ad


def test_resolve_daily_limit_default_and_zero():
    assert ad.resolve_daily_limit({}) == ad.DEFAULT_DAILY_LIMIT
    assert ad.resolve_daily_limit({"web_crawler_account_stub_daily_limit": 0}) == 0
    assert ad.resolve_daily_limit({"web_crawler_account_stub_daily_limit": "30"}) == 30


def test_daily_used_cross_day_resets(monkeypatch):
    store: dict[str, str] = {}

    class _Conn:
        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(ad, "connect", lambda: _Conn())
    monkeypatch.setattr(
        ad, "get_setting", lambda conn, key, default="": store.get(key, default)
    )
    monkeypatch.setattr(
        ad,
        "set_setting",
        lambda conn, key, value: store.__setitem__(key, value),
    )

    assert ad.daily_used("sehuatang", today="2026-07-31") == 0
    assert ad.note_daily_attempt("sehuatang", today="2026-07-31") == 1
    assert ad.note_daily_attempt("sehuatang", today="2026-07-31", n=2) == 3
    assert ad.daily_used("sehuatang", today="2026-07-31") == 3
    # 跨日清零
    assert ad.daily_used("sehuatang", today="2026-08-01") == 0
    st = ad.daily_status("sehuatang", 50, today="2026-07-31")
    assert st["used"] == 3
    assert st["remaining"] == 47
    assert st["exhausted"] is False
    st2 = ad.daily_status("sehuatang", 3, today="2026-07-31")
    assert st2["exhausted"] is True
    assert ad.daily_remaining("sehuatang", 0, today="2026-07-31") is None
