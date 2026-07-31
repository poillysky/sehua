"""多附件加速：列表无权早停、连续空转早停、Flare 同帖只试一次。"""

from __future__ import annotations

import asyncio

import pytest

from parsers.attachments import DownloadAttachment, listing_shows_attach_denied


def test_listing_shows_attach_denied_in_tattl():
    html = """
    <html><body>
    <div id="postmessage_1">见附件</div>
    <div class="tattl attnm">
      <a href="forum.php?mod=attachment&amp;aid=MQ==">links.txt</a>
      <p>抱歉，只有特定用户可以下载本站附件</p>
    </div>
    Powered by Discuz!
    </body></html>
    """
    assert listing_shows_attach_denied(html) is True


def test_listing_readperm_alone_not_denied():
    """「阅读权限: 10」只是门槛，不能当无权占位。"""
    html = """
    <html><body>
    <div id="postmessage_1">见附件</div>
    <div class="tattl">
      <a href="forum.php?mod=attachment&amp;aid=MQ==">a.txt</a>
      <p>7.45 KB, 阅读权限: 10 , 下载次数: 110</p>
    </div>
    Powered by Discuz!
    </body></html>
    """
    assert listing_shows_attach_denied(html) is False


@pytest.mark.asyncio
async def test_download_tail_listing_denied_skips_download(monkeypatch):
    from crawler import attachments as mod

    called = {"n": 0}

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("should not download")

    monkeypatch.setattr(downloader, "_download_one", boom)

    html = """
    <html><body>
    <div id="postmessage_1">见附件</div>
    <div class="tattl">
      <a href="forum.php?mod=attachment&amp;aid=1">a.txt</a>
      您所在的用户组无法下载或查看附件
    </div>
    Powered by Discuz!
    </body></html>
    """
    res = await downloader.download_tail(html, "http://example/thread")
    assert res.denied is True
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_download_tail_empty_streak_stops(monkeypatch):
    from crawler import attachments as mod

    monkeypatch.setattr(mod, "ATTACH_EMPTY_STREAK_STOP", 3)
    monkeypatch.setattr(mod, "ATTACH_POLL_WALL_SEC", 60.0)

    atts = [
        DownloadAttachment(name=f"f{i}.txt", url=f"http://x/{i}", kind="txt")
        for i in range(6)
    ]
    tried: list[str] = []
    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)
    monkeypatch.setattr(mod, "listing_shows_attach_denied", lambda *_a, **_k: False)

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def empty_one(attachment, timeout, passwords=None):
        tried.append(attachment.name)
        return ("", False, False, False, False, False, True)

    monkeypatch.setattr(downloader, "_download_one", empty_one)

    html = "<html><body><div id='postmessage_1'>x</div>Powered by Discuz!</body></html>"
    res = await downloader.download_tail(html, "http://example/thread")
    assert tried == ["f0.txt", "f1.txt", "f2.txt"]
    assert res.tried_names == ["f0.txt", "f1.txt", "f2.txt"]
    assert res.empty_attachment is True
    assert res.failed is False


@pytest.mark.asyncio
async def test_skip_flare_after_first_miss(monkeypatch):
    from crawler import attachments as mod
    from parsers.attachments import DownloadAttachment as DA

    class FakeSession:
        _ready = True
        cookies: dict = {}

        async def run_on_page(self, fn, *, timeout=None):
            return None, False, False, False, False

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]
    flare_calls = {"n": 0}

    def fake_flare(url):
        flare_calls["n"] += 1
        return None, False, False, False, False

    monkeypatch.setattr(downloader, "_fetch_bytes_via_flare", fake_flare)

    async def fake_ui(*_a, **_k):
        return None, False, False, False, False

    monkeypatch.setattr(downloader, "_download_raw_via_ui", fake_ui)

    a1 = DA(name="a.txt", url="http://x/1", kind="txt")
    a2 = DA(name="b.txt", url="http://x/2", kind="txt")
    await downloader._download_one(a1, 10)
    assert flare_calls["n"] == 1
    assert downloader._skip_flare is True
    await downloader._download_one(a2, 10)
    assert flare_calls["n"] == 1


@pytest.mark.asyncio
async def test_skip_flare_when_cf_clearance_present(monkeypatch):
    """浏览器已有 cf_clearance：fetch 空也不打 Flare。"""
    from crawler import attachments as mod
    from parsers.attachments import DownloadAttachment as DA

    class FakeSession:
        _ready = True
        cookies = {"cf_clearance": "abc"}

        async def run_on_page(self, fn, *, timeout=None):
            return None, False, False, False, False

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]
    flare_calls = {"n": 0}

    def fake_flare(url):
        flare_calls["n"] += 1
        return None, False, False, False, False

    monkeypatch.setattr(downloader, "_fetch_bytes_via_flare", fake_flare)

    async def fake_ui(*_a, **_k):
        return None, False, False, False, False

    monkeypatch.setattr(downloader, "_download_raw_via_ui", fake_ui)

    await downloader._download_one(DA(name="a.txt", url="http://x/1", kind="txt"), 10)
    assert flare_calls["n"] == 0


def test_attach_fetch_ms_shorter_than_page_op():
    from crawler import attachments as mod

    assert mod.ATTACH_FETCH_MS == 12_000
    assert mod.ATTACH_FETCH_MS < int(mod.ATTACH_PAGE_OP_SEC * 1000) - 2000


def test_filter_all_link_attachments_skip_names():
    from parsers.attachments import DownloadAttachment, filter_all_link_attachments

    atts = [
        DownloadAttachment("a.txt", "u1", "txt"),
        DownloadAttachment("seed.torrent", "u2", "torrent"),
        DownloadAttachment("b.txt", "u3", "txt"),
    ]
    got = filter_all_link_attachments(
        atts, preferred_link="magnet", skip_names=["a.txt", "b.txt"]
    )
    assert [a.name for a in got] == ["seed.torrent"]


def test_archive_member_link_name_priority():
    from crawler.attachments import _link_member_names_in_archive

    names = [
        "readme.txt",
        "合集115ed2k.txt",
        "notes.txt",
        "backup.zip",  # not a link member type for this helper's groups
    ]
    got = _link_member_names_in_archive(names)
    assert got[0] == "合集115ed2k.txt"
    assert "readme.txt" in got
    assert got.index("合集115ed2k.txt") < got.index("readme.txt")