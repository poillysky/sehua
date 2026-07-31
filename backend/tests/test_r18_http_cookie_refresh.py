"""R18 壳重试必须带上新写的 _safe cookie。"""

from __future__ import annotations

import sys
from types import ModuleType

from crawler.fetcher import Fetcher


class _FakeSession:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {"safe": "1"}
        self.user_agent = "Mozilla/5.0"
        self.saved = 0

    def update(self, cookies: dict[str, str]) -> None:
        self.cookies.update({k: v for k, v in cookies.items() if v})

    def save(self) -> None:
        self.saved += 1


class _Resp:
    def __init__(self, body: str) -> None:
        self.content = body.encode("utf-8")
        self.encoding = "utf-8"
        self.status_code = 200
        self.cookies = {}


def test_http_get_r18_retry_refreshes_cookies(monkeypatch) -> None:
    shell = (
        "<html><title>提示</title><script>var safeid = 'abc123safeidxx';</script>"
        + ("x" * 100)
    )
    real = (
        '<html><span id="thread_subject">t</span>'
        '<div id="postlist"><td class="t_f" id="postmessage_1">body</td>'
        "</div>Powered by Discuz!</html>"
    )
    seen_cookies: list[dict] = []

    def fake_get(url, **kwargs):
        jar = dict(kwargs.get("cookies") or {})
        seen_cookies.append(jar)
        if jar.get("_safe") == "abc123safeidxx":
            return _Resp(real)
        return _Resp(shell)

    fake_curl = ModuleType("curl_cffi")
    fake_requests = ModuleType("curl_cffi.requests")
    fake_requests.get = fake_get
    fake_curl.requests = fake_requests
    monkeypatch.setitem(sys.modules, "curl_cffi", fake_curl)
    monkeypatch.setitem(sys.modules, "curl_cffi.requests", fake_requests)

    f = Fetcher(_FakeSession())  # type: ignore[arg-type]
    html = f._http_get("https://www.sehuatang.net/thread-1-1-1.html")

    assert "postmessage" in html
    assert len(seen_cookies) == 2
    assert seen_cookies[0].get("_safe") != "abc123safeidxx"
    assert seen_cookies[1].get("_safe") == "abc123safeidxx"
    assert f.session.cookies.get("_safe") == "abc123safeidxx"
    assert f.session.saved >= 1
