"""List fetch: HTTP first, browser fallback."""

from __future__ import annotations

import asyncio

from crawler.fetcher import Fetcher, detect_fetch_mode


def test_detect_fetch_mode_list_is_http() -> None:
    assert detect_fetch_mode("https://www.sehuatang.net/forum-103-1.html") == "http"
    assert (
        detect_fetch_mode(
            "https://www.sehuatang.net/forum.php?mod=forumdisplay&fid=103&typeid=480"
        )
        == "http"
    )
    assert detect_fetch_mode("https://www.sehuatang.net/thread-1-1-1.html") == "http"
    assert detect_fetch_mode("https://www.sehuatang.net/") == "browser"


def test_get_list_html_uses_http_when_valid(monkeypatch) -> None:
    class _Sess:
        _ready = True

        def save(self) -> None:
            return None

        @staticmethod
        def is_safe_shell(html: str) -> bool:
            return False

    f = Fetcher(_Sess())  # type: ignore[arg-type]
    calls: list[str] = []

    async def fake_http(url: str, *, raise_on_shell: bool = True) -> str:
        del raise_on_shell
        calls.append("http")
        return (
            "<html><body>Powered by Discuz!"
            '<a href="thread-123-1-1.html">t</a></body></html>'
        )

    async def fake_browser(url: str, *, raise_on_shell: bool = True) -> str:
        del raise_on_shell
        calls.append("browser")
        return ""

    monkeypatch.setattr(f, "_get_http", fake_http)
    monkeypatch.setattr(f, "_get_browser", fake_browser)

    html = asyncio.run(
        f.get_list_html("https://www.sehuatang.net/forum-103-1.html", retries=1)
    )
    assert "thread-123" in html
    assert calls == ["http"]
    assert f.last_list_browser_fallback is False


def test_get_list_html_falls_back_to_browser(monkeypatch) -> None:
    class _Sess:
        _ready = True

        def save(self) -> None:
            return None

        @staticmethod
        def is_safe_shell(html: str) -> bool:
            return "safeid" in html

    f = Fetcher(_Sess())  # type: ignore[arg-type]
    calls: list[str] = []

    async def fake_http(url: str, *, raise_on_shell: bool = True) -> str:
        del raise_on_shell
        calls.append("http")
        return "<html>var safeid='x'</html>"

    async def fake_browser(url: str, *, raise_on_shell: bool = True) -> str:
        del raise_on_shell
        calls.append("browser")
        return (
            "<html>Powered by Discuz!"
            '<a href="thread-9-1-1.html">ok</a></html>'
        )

    monkeypatch.setattr(f, "_get_http", fake_http)
    monkeypatch.setattr(f, "_get_browser", fake_browser)

    html = asyncio.run(
        f.get_list_html("https://www.sehuatang.net/forum-103-1.html", retries=1)
    )
    assert "thread-9" in html
    assert calls == ["http", "browser"]
    assert f.last_list_browser_fallback is True
