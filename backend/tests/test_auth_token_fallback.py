"""Auth should fall back from invalid Bearer to valid Cookie."""

from __future__ import annotations

from auth import deps


class _Req:
    def __init__(self, *, authorization: str = "", cookie: str | None = None) -> None:
        self.headers = {"Authorization": authorization} if authorization else {}
        self.cookies = {deps.cookie_name(): cookie} if cookie else {}


def test_invalid_bearer_falls_back_to_cookie(monkeypatch) -> None:
    monkeypatch.setattr(deps, "auth_required", lambda: True)

    def fake_decode(token: str):
        if token == "good-cookie":
            return {"sub": "7", "username": "admin", "roles": ["admin"]}
        return None

    monkeypatch.setattr(deps, "decode_access_token", fake_decode)
    req = _Req(authorization="Bearer bad-bearer", cookie="good-cookie")
    user = deps.get_current_user(req)  # type: ignore[arg-type]
    assert user is not None
    assert user["id"] == 7
    assert user["username"] == "admin"


def test_both_invalid_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(deps, "auth_required", lambda: True)
    monkeypatch.setattr(deps, "decode_access_token", lambda _t: None)
    req = _Req(authorization="Bearer x", cookie="y")
    assert deps.get_current_user(req) is None  # type: ignore[arg-type]
