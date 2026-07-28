# -*- coding: utf-8 -*-
"""多附件：合并试算仍不合格则继续下后面附件；合格则停。"""

from __future__ import annotations

import asyncio

from parsers.attachments import DownloadAttachment


def test_attach_merge_still_unqualified_preview_gap():
    """×3 标题却多链未按名分预览 → 试算不合格，应继续。"""
    from crawler.attachments import _attach_merge_still_unqualified

    title = "精选合集 ×3"
    html = (
        f"<html><body><span id='thread_subject'>{title}</span>"
        "<div id='postmessage_1'>【影片大小】：3.00GB<br>"
        "<img src='http://a.jpg'></div></body></html>"
    )
    three = "\n".join(
        "magnet:?xt=urn:btih:" + (ch * 40) + "&xl=1073741824" for ch in "ABC"
    )
    assert _attach_merge_still_unqualified(html, three, preferred_link="magnet") is True


def test_attach_merge_ok_single_with_size_preview():
    """单链 + 大小 + 预览 → 试算合格，可停。"""
    from crawler.attachments import _attach_merge_still_unqualified

    html = (
        "<html><body><span id='thread_subject'>好片 ABC-001</span>"
        "<div id='postmessage_1'>【影片名称】：好片 ABC-001<br>【影片大小】：2.00GB<br>"
        "<img src='http://example.com/p.jpg'></div></body></html>"
    )
    good = "magnet:?xt=urn:btih:" + ("B" * 40) + "&xl=" + str(2 * 1024**3)
    assert _attach_merge_still_unqualified(html, good, preferred_link="magnet") is False


def test_download_tail_continues_when_merge_unqualified(monkeypatch):
    """附件1有链但不合格 → 继续下附件2合并；合格后停。"""
    from crawler import attachments as mod

    html = (
        "<html><body><span id='thread_subject'>双附件帖</span>"
        "<div id='postmessage_1'>正文无链<br>"
        "<img src='http://a.jpg'></div>"
        "<ignore_js_op>"
        "<a href='forum.php?mod=attachment&aid=1'>a.txt</a>"
        "<a href='forum.php?mod=attachment&aid=2'>b.txt</a>"
        "</ignore_js_op></body></html>"
    )
    atts = [
        DownloadAttachment(name="a.txt", url="http://x/1", kind="txt"),
        DownloadAttachment(name="b.txt", url="http://x/2", kind="txt"),
    ]
    texts = {
        "a.txt": "magnet:?xt=urn:btih:" + ("A" * 40) + "&xl=1073741824",
        "b.txt": "magnet:?xt=urn:btih:" + ("B" * 40) + "&xl=1073741824",
    }
    tried: list[str] = []
    preview_calls: list[str] = []

    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)

    def fake_preview(html_s, attach_text, **_k):
        preview_calls.append(attach_text)
        # 仅第一份链 → 不合格；合并到第二份后合格
        return "A" * 40 in attach_text and "B" * 40 not in attach_text

    monkeypatch.setattr(mod, "_attach_merge_still_unqualified", fake_preview)

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def fake_one(attachment, timeout, passwords=None):
        tried.append(attachment.name)
        return texts[attachment.name], False, True, False

    monkeypatch.setattr(downloader, "_download_one", fake_one)

    res = asyncio.run(
        downloader.download_tail(html, "http://example/thread", preferred_link="magnet")
    )
    assert tried == ["a.txt", "b.txt"]
    assert len(preview_calls) >= 1
    assert "A" * 40 in (res.text or "")
    assert "B" * 40 in (res.text or "")
    assert res.downloaded is True


def test_download_tail_stops_when_merge_qualified(monkeypatch):
    """附件1有链且试算合格 → 不再下附件2。"""
    from crawler import attachments as mod

    html = (
        "<html><body><span id='thread_subject'>单好链</span>"
        "<div id='postmessage_1'>正文无链</div>"
        "<ignore_js_op>"
        "<a href='forum.php?mod=attachment&aid=1'>a.txt</a>"
        "<a href='forum.php?mod=attachment&aid=2'>b.txt</a>"
        "</ignore_js_op></body></html>"
    )
    atts = [
        DownloadAttachment(name="a.txt", url="http://x/1", kind="txt"),
        DownloadAttachment(name="b.txt", url="http://x/2", kind="txt"),
    ]
    tried: list[str] = []
    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)
    monkeypatch.setattr(
        mod, "_attach_merge_still_unqualified", lambda *_a, **_k: False
    )

    class FakeSession:
        _ready = True

    downloader = mod.AttachmentDownloader(FakeSession())  # type: ignore[arg-type]

    async def fake_one(attachment, timeout, passwords=None):
        tried.append(attachment.name)
        return (
            "magnet:?xt=urn:btih:" + ("A" * 40) + "&xl=1073741824",
            False,
            True,
            False,
        )

    monkeypatch.setattr(downloader, "_download_one", fake_one)

    res = asyncio.run(
        downloader.download_tail(html, "http://example/thread", preferred_link="magnet")
    )
    assert tried == ["a.txt"]
    assert "A" * 40 in (res.text or "")
    assert res.downloaded is True
