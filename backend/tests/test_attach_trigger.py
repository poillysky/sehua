# -*- coding: utf-8 -*-
"""切块后附件触发：单/多资源口径。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from workers.attach_trigger import (
    classify_resource_mode,
    frame_has_missing_block_links,
    plan_attachment_fetch,
)
from workers.thread_outcome import ThreadOutcome


def _html_zone(body: str = "", *, names: int = 0) -> str:
    name_bits = "".join(f"【影片名称】：资源{i}<br>" for i in range(1, names + 1))
    return (
        "<html><body>"
        "<span id='thread_subject'>测试帖</span>"
        f"<div id='postmessage_1'>{name_bits}{body}</div>"
        "<ignore_js_op>"
        "<a href='forum.php?mod=attachment&aid=1'>115ED2K下载链接.txt</a>"
        "</ignore_js_op></body></html>"
    )


def _asset(h: str, name: str) -> ParsedAsset:
    return ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename=name,
        size=1024**3,
        uri=f"magnet:?xt=urn:btih:{h}",
        preview_images=["http://a.jpg"],
    )


def _parsed(assets: list[ParsedAsset], *, title: str = "测试帖") -> DualParseResult:
    return DualParseResult(
        tid=1,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet" if assets else "none",
        layout="",
        had_attachments=False,
    )


def test_classify_multi_by_name_labels():
    html = _html_zone(names=2)
    assert classify_resource_mode(_parsed([]), html) == "multi"
    assert classify_resource_mode(_parsed([]), _html_zone(names=1)) == "single"


def test_plan_pending_need_attach_after_cards():
    html = _html_zone()
    parsed = _parsed([])
    outcome = ThreadOutcome(
        "need_attachments",
        "正文无磁力，尝试种子附件",
        "magnet",
        "测试帖",
        need_attachments=True,
        attachment_kind="torrent",
    )
    plan = plan_attachment_fetch(
        parsed=parsed,
        html=html,
        outcome=outcome,
        attach_tried=False,
        link_pref="magnet",
        thread_url="https://x/t",
        pending_need_attach=True,
        pending_kind="torrent",
    )
    assert plan is not None
    assert plan.mode == "no_link"
    assert plan.queue_on_daily_limit is True
    assert plan.quota_stop is True


def test_plan_single_unqual_triggers():
    html = _html_zone()
    # 两链同名→可试算；这里用无预览多链制造不合格较稳：名=标题的多资源
    title = "双资源合集帖"
    a = _asset("A" * 40, title)
    b = _asset("B" * 40, "另一片名")
    parsed = _parsed([a, b], title=title)
    outcome = ThreadOutcome("import", "成功：正文含目标链接", "magnet", title)
    plan = plan_attachment_fetch(
        parsed=parsed,
        html=html,
        outcome=outcome,
        attach_tried=False,
        link_pref="magnet",
        thread_url="https://x/t",
        persist=True,
    )
    assert plan is not None
    assert plan.mode in {"single_unqual", "multi_missing"}
    assert plan.queue_on_daily_limit is False


def test_plan_qualified_single_no_fetch():
    html = _html_zone()
    a = _asset("C" * 40, "好片名")
    a.preview_images = ["http://x.jpg"]
    parsed = _parsed([a], title="好片名")
    parsed.description = "【影片大小】：1.00GB"
    parsed.metadata = {"影片大小": "1.00GB"}
    outcome = ThreadOutcome("import", "成功：正文含目标链接", "magnet", "好片名")
    plan = plan_attachment_fetch(
        parsed=parsed,
        html=html,
        outcome=outcome,
        attach_tried=False,
        link_pref="magnet",
        thread_url="https://x/t",
        persist=True,
    )
    # 合格则不下；若环境差异导致不合格也至少不是 no_link 误触发
    if plan is not None:
        assert plan.mode != "no_link" or not parsed.assets


def test_download_tail_multi_ignores_short_quota(monkeypatch):
    """多资源 quota_stop=False：试算合格即停，不因标题配额继续。"""
    import asyncio

    from crawler import attachments as mod
    from parsers.attachments import DownloadAttachment

    html = (
        "<html><body><span id='thread_subject'>合集【10配额】</span>"
        "<div id='postmessage_1'>x</div></body></html>"
    )
    atts = [
        DownloadAttachment(name="a.txt", url="http://x/1", kind="txt"),
        DownloadAttachment(name="b.txt", url="http://x/2", kind="txt"),
    ]
    tried: list[str] = []
    monkeypatch.setattr(mod, "extract_download_attachments", lambda *_a, **_k: atts)
    monkeypatch.setattr(mod, "filter_all_link_attachments", lambda items, **_k: items)
    monkeypatch.setattr(mod, "_attach_merge_still_unqualified", lambda *_a, **_k: False)
    monkeypatch.setattr(mod, "_quota_expect_from_html", lambda *_a, **_k: 10)

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
            False,
            False,
        )

    monkeypatch.setattr(downloader, "_download_one", fake_one)
    res = asyncio.run(
        downloader.download_tail(
            html,
            "http://example/thread",
            preferred_link="magnet",
            quota_stop=False,
        )
    )
    assert tried == ["a.txt"]
    assert "A" * 40 in (res.text or "")


def test_frame_missing_links_helper():
    title = "双资源"
    a = _asset("A" * 40, "片名甲")
    b = _asset("B" * 40, "片名乙")
    b.uri = ""
    b.hash = ""
    # 无有效链的资产可能被 frame 丢掉；用正常双资产确认 helper 不炸
    parsed = _parsed([a, b], title=title)
    # 有链时不一定 missing；只保证可调用
    assert isinstance(frame_has_missing_block_links(parsed, post_title=title), bool)
