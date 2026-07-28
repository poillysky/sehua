# -*- coding: utf-8 -*-
"""正文有链但填槽不合格 → 再下附件复判。"""

from __future__ import annotations

import asyncio

from db.persist import build_parse_frame, preview_frame_outcome
from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import format_frame_outcome


def _asset(h: str, name: str, *, size: int = 10 * 1024 * 1024) -> ParsedAsset:
    # 勿把中文塞进 dn=，否则 resolve_sub_filename 会误回帖标题
    return ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename=name,
        size=size,
        uri=f"magnet:?xt=urn:btih:{h}",
        preview_images=[],
    )


def test_preview_frame_outcome_unqualified_multi_name_eq_title():
    """多资源名=帖标题 → 试算不合格：资源名。"""
    title = "双资源合集帖"
    a = _asset("A" * 40, title, size=1024**3)
    a.preview_images = ["http://a.jpg"]
    b = _asset("B" * 40, "另一片名", size=1024**3)
    b.preview_images = ["http://b.jpg"]
    parsed = DualParseResult(
        tid=1,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg", "http://b.jpg"],
        extract_password="",
        assets=[a, b],
        primary_link_kind="magnet",
        layout="",
        had_attachments=False,
    )
    out = preview_frame_outcome(parsed, import_outcome="成功：正文含目标链接")
    assert out.startswith("不合格")
    frame = build_parse_frame(parsed, post_title=title)
    assert frame is not None
    assert frame.spec.kind.startswith("multi")
    assert format_frame_outcome("成功：试判", frame).startswith("不合格")


def test_preview_frame_outcome_ok_pack_name_eq_title():
    """单资源名=帖标题允许 → 不因资源名硬失败。"""
    title = "单资源帖"
    a = _asset("C" * 40, title, size=2 * 1024**3)
    a.preview_images = ["http://x.jpg"]
    parsed = DualParseResult(
        tid=2,
        title=title,
        description="【影片大小】：2.00GB",
        metadata={"影片大小": "2.00GB"},
        preview_images=["http://x.jpg"],
        extract_password="",
        assets=[a],
        primary_link_kind="magnet",
        layout="",
        had_attachments=False,
    )
    out = preview_frame_outcome(parsed, import_outcome="成功：正文含目标链接")
    assert not out.startswith("不合格：资源名")


def test_attach_rejudge_uses_attach_when_body_unqualified(monkeypatch):
    """不合格试算后下附件，合并解析可换成附件结果。"""
    calls: list[str] = []

    class FakeAttachRes:
        text = "magnet:?xt=urn:btih:" + ("D" * 40)
        denied = False
        failed = False
        downloaded = True
        login_required = False

    async def fake_fetch(*_a, **_k):
        calls.append("fetch")
        return FakeAttachRes()

    async def fake_parse(*_a, **_k):
        a0 = _asset("D" * 40, "正确片名", size=1024**3)
        a0.preview_images = ["http://p.jpg"]
        return DualParseResult(
            tid=9,
            title="双资源合集帖",
            description="",
            metadata={},
            preview_images=["http://p.jpg"],
            extract_password="",
            assets=[a0],
            primary_link_kind="magnet",
            layout="",
            had_attachments=True,
        )

    monkeypatch.setattr(
        "crawler.attachments.fetch_attachments_for_outcome", fake_fetch
    )

    title = "双资源合集帖"
    a = _asset("A" * 40, title, size=1024**3)
    a.preview_images = ["http://a.jpg"]
    b = _asset("B" * 40, "另一片名", size=1024**3)
    b.preview_images = ["http://b.jpg"]
    parsed = DualParseResult(
        tid=9,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg", "http://b.jpg"],
        extract_password="",
        assets=[a, b],
        primary_link_kind="magnet",
        layout="",
        had_attachments=False,
    )
    assert preview_frame_outcome(parsed).startswith("不合格")

    async def _run() -> None:
        from crawler.attachments import fetch_attachments_for_outcome

        res = await fetch_attachments_for_outcome(
            None,
            html="<html>attach</html>",
            thread_url="https://x/t",
            attachment_kind="torrent",
            timeout=15,
            preferred_link="magnet",
        )
        merged = await fake_parse()
        assert res.text and merged.assets
        assert not preview_frame_outcome(merged).startswith("不合格：资源名")

    asyncio.run(_run())
    assert calls == ["fetch"]
