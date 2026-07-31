"""附件：读帖 HTML 足够时延后开帖；HTTP 直拉可免导航。"""

from __future__ import annotations

import asyncio


def test_fetch_attachments_skips_nav_when_http_zone(monkeypatch):
    from crawler import attachments as mod
    from parsers.attachments import AttachmentFetchResult

    html = (
        "<html><body>"
        + ("x" * 9000)
        + '<div id="postmessage_1">见附件</div>'
        '<div class="tattl attnm">'
        '<a href="https://www.sehuatang.net/forum.php?mod=attachment&aid=MQ==">'
        "a.txt</a></div>"
        "Powered by Discuz!</body></html>"
    )

    class FakeSession:
        _ready = True
        cookies = {"safe": "1", "_safe": "abc", "cf_clearance": "x"}
        user_agent = "Mozilla/5.0"
        proxy = ""

    ensured = {"n": 0}

    async def boom_ensure(self, *a, **k):
        ensured["n"] += 1
        raise AssertionError("should not navigate upfront")

    monkeypatch.setattr(mod.AttachmentDownloader, "ensure_thread_page", boom_ensure)

    async def fake_tail(self, *a, **k):
        return AttachmentFetchResult(text="ed2k://|file|a.mkv|1|AABB|/", downloaded=True)

    monkeypatch.setattr(mod.AttachmentDownloader, "download_tail", fake_tail)

    async def _run():
        res = await mod.fetch_attachments_for_outcome(
            FakeSession(),  # type: ignore[arg-type]
            html=html,
            thread_url="https://www.sehuatang.net/thread-1-1-1.html",
            attachment_kind="txt_tail",
        )
        assert res.downloaded is True
        assert ensured["n"] == 0

    asyncio.run(_run())


def test_skip_page_fetch_when_not_on_thread(monkeypatch):
    from crawler import attachments as mod
    from parsers.attachments import DownloadAttachment

    class FakeSession:
        _ready = True
        cookies = {"safe": "1", "_safe": "abc", "cf_clearance": "x"}
        user_agent = "Mozilla/5.0"
        proxy = ""

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]
    downloader._thread_url = "https://www.sehuatang.net/thread-1-1-1.html"
    downloader._thread_page_ready = False

    monkeypatch.setattr(
        mod.AttachmentDownloader,
        "_fetch_bytes_via_curl",
        lambda self, url, *, referer="": (None, False, False, False, False),
    )

    called_page = {"n": 0}

    async def boom_page(self, *a, **k):
        called_page["n"] += 1
        raise AssertionError("page fetch should be skipped")

    monkeypatch.setattr(mod.AttachmentDownloader, "_fetch_bytes_via_page", boom_page)

    ensured = {"n": 0}

    async def fake_ensure(self):
        ensured["n"] += 1
        self._thread_page_ready = True

    monkeypatch.setattr(mod.AttachmentDownloader, "_ensure_thread_for_ui", fake_ensure)

    async def fake_ui(self, *a, **k):
        return (
            b"ed2k://|file|a.mkv|1|AABBCCDDEEFF00112233445566778899|/",
            False,
            False,
            False,
            False,
        )

    monkeypatch.setattr(mod.AttachmentDownloader, "_download_raw_via_ui", fake_ui)

    async def fake_extract(self, att, data, passwords=None):
        return data.decode("utf-8", errors="ignore")

    monkeypatch.setattr(mod.AttachmentDownloader, "_extract_attachment_text", fake_extract)

    att = DownloadAttachment(
        name="a.txt",
        url="https://www.sehuatang.net/forum.php?mod=attachment&aid=1",
        kind="txt",
    )

    async def _run():
        text, _denied, downloaded, *_ = await downloader._download_one(att, 30)
        assert called_page["n"] == 0
        assert ensured["n"] >= 1
        assert downloaded is True
        assert "ed2k://" in text

    asyncio.run(_run())


def test_http_curl_denied_is_terminal(monkeypatch):
    from crawler import attachments as mod
    from parsers.attachments import DownloadAttachment

    class FakeSession:
        _ready = True
        cookies = {"safe": "1", "_safe": "abc", "cf_clearance": "x"}
        user_agent = "Mozilla/5.0"
        proxy = ""

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]
    downloader._thread_url = "https://www.sehuatang.net/thread-1-1-1.html"

    def fake_curl(self, url, *, referer=""):
        tip = "<html>抱歉，本附件您无权下载与浏览</html>"
        from parsers.attachments import is_attachment_denied

        assert is_attachment_denied(tip)
        return None, True, False, False, False

    monkeypatch.setattr(mod.AttachmentDownloader, "_fetch_bytes_via_curl", fake_curl)

    called_page = {"n": 0}

    async def boom_page(self, *a, **k):
        called_page["n"] += 1
        raise AssertionError("no page after http denied")

    monkeypatch.setattr(mod.AttachmentDownloader, "_fetch_bytes_via_page", boom_page)

    att = DownloadAttachment(
        name="a.txt",
        url="https://www.sehuatang.net/forum.php?mod=attachment&aid=1",
        kind="txt",
    )

    async def _run():
        text, denied, *_rest = await downloader._download_one(att, 30)
        assert denied is True
        assert text == ""
        assert called_page["n"] == 0

    asyncio.run(_run())
