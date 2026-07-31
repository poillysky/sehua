"""多附件轮询墙钟 / 单附件超时：防卡死。"""

from __future__ import annotations

import asyncio

import pytest

from parsers.attachments import DownloadAttachment


@pytest.mark.asyncio
async def test_download_tail_wall_deadline_stops(monkeypatch):
    from crawler import attachments as mod

    monkeypatch.setattr(mod, "ATTACH_POLL_WALL_SEC", 0.45)
    monkeypatch.setattr(mod, "ATTACH_ONE_WALL_SEC", 2.0)

    atts = [
        DownloadAttachment(name=f"f{i}.txt", url=f"http://x/{i}", kind="txt")
        for i in range(8)
    ]
    tried: list[str] = []

    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def slow_one(attachment, timeout, passwords=None):
        tried.append(attachment.name)
        await asyncio.sleep(0.15)
        return ("", False, False, False, False, False, False)

    monkeypatch.setattr(downloader, "_download_one", slow_one)

    html = "<html><body><div id='postmessage_1'>x</div>Powered by Discuz!</body></html>"
    res = await downloader.download_tail(html, "http://example/thread")
    assert len(tried) < len(atts)
    assert len(tried) >= 1
    assert res.failed is True


@pytest.mark.asyncio
async def test_download_tail_one_timeout_continues(monkeypatch):
    from crawler import attachments as mod

    monkeypatch.setattr(mod, "ATTACH_POLL_WALL_SEC", 30.0)
    monkeypatch.setattr(mod, "ATTACH_ONE_WALL_SEC", 0.2)

    atts = [
        DownloadAttachment(name="hang.txt", url="http://x/1", kind="txt"),
        DownloadAttachment(name="ok.txt", url="http://x/2", kind="txt"),
    ]
    tried: list[str] = []
    magnet = "magnet:?xt=urn:btih:" + ("C" * 40)

    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)
    monkeypatch.setattr(mod, "_attach_merge_still_unqualified", lambda *_a, **_k: False)

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def maybe_hang(attachment, timeout, passwords=None):
        tried.append(attachment.name)
        if attachment.name == "hang.txt":
            await asyncio.sleep(2.0)
            return ("", False, False, False, False, False, False)
        return (magnet, False, True, False, False, False, False)

    monkeypatch.setattr(downloader, "_download_one", maybe_hang)

    html = "<html><body><div id='postmessage_1'>x</div>Powered by Discuz!</body></html>"
    res = await downloader.download_tail(
        html, "http://example/thread", preferred_link="magnet", quota_stop=False
    )
    assert tried == ["hang.txt", "ok.txt"]
    assert magnet in (res.text or "")
    assert res.downloaded is True
