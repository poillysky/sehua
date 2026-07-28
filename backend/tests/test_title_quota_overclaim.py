# -*- coding: utf-8 -*-
"""标题配额与实链差 → 不合格：待核（兜底，非硬确认四类）。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def _ed2k(h: str, name: str, size: int, *, prev: bool = False) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}|{size}|{h}|/",
        preview_images=["http://a.jpg"] if prev else [],
    )


def test_body_only_title_quota_overclaim_is_soft():
    """无附件：标题 59 配额、正文 55 链 → 不合格：待核，不结构失败（tid=3471583）。"""
    title = "合集【163V/61G/59配额】"
    sz = 50 * 1024 * 1024
    assets = [
        _ed2k(f"{i:032X}", f"v{i}.mp4", sz, prev=(i == 0)) for i in range(55)
    ]
    parsed = DualParseResult(
        tid=3471583,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="ed2k",
        layout="title_then_magnet",
        had_attachments=False,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, assets[0], assets)],
        had_attachments=False,
    )
    assert frame.spec.source == "body"
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    out = format_frame_outcome("成功：正文含目标链接", frame)
    assert out.startswith("不合格：待核")
    assert any("不一致" in w or "待核" in w for w in frame.verdict.soft_warnings)


def test_attach_short_quota_is_soft_review():
    """有附件来源仍短于配额 → 同样不合格：待核。"""
    title = "合集【10配额】"
    sz = 10 * 1024 * 1024
    assets = [
        _ed2k(f"{i:032X}", f"v{i}.mp4", sz, prev=(i == 0)) for i in range(5)
    ]
    parsed = DualParseResult(
        tid=1,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, assets[0], assets)],
        had_attachments=True,
    )
    assert frame.spec.source == "attach"
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("不合格：待核")
    assert any("附件" in w and ("不一致" in w or "待核" in w) for w in frame.verdict.soft_warnings)
