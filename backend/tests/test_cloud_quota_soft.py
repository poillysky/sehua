# -*- coding: utf-8 -*-
"""混合网盘标题的配额口径：不全等于 ed2k 链数。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def _ed2k(h: str, name: str, size: int) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}.rar|{size}|{h}|/",
        preview_images=["http://a.jpg"],
    )


def test_cloud_mixed_quota_mismatch_is_soft():
    """【115eD2k/夸克/迅雷】3配额但仅2条 ed2k → 软提醒，不结构失败（tid=3337537）。"""
    title = "【整理】【115eD2K/夸克/迅雷】三部合集【32.9G/3Games/3配额】"
    sz = int(16 * 1024**3)
    a = _ed2k("A" * 32, "pack-a", sz)
    b = _ed2k("B" * 32, "pack-b", sz)
    b.preview_images = []
    parsed = DualParseResult(
        tid=3337537,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a, b],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("三部合集", a, [a, b])],
        had_attachments=True,
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "info:cloud_quota_soft" in frame.verdict.tags
    assert not any("漏链" in e for e in frame.verdict.hard_errors)
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    # 云盘混合配额差：结构过门 → 成功 + 提醒，勿升格不合格：待核
    assert out.startswith("成功")
    assert "提醒:" in out and "配额" in out
    assert not out.startswith("不合格")


def test_pure_115ed2k_tag_quota_mismatch_is_overclaim_not_cloud():
    """纯【115eD2k】标不是云盘混合：链数不足 → title_overclaim，勿 cloud_soft（tid=3485915）。"""
    title = "【整理】【115eD2k】斗鱼合集【194GB/182V/182配额】"
    sz = int(1024**3)
    assets = [_ed2k(f"{i:032X}", f"v{i}", sz) for i in range(43)]
    for a in assets[1:]:
        a.preview_images = []
    parsed = DualParseResult(
        tid=3485915,
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
        named_groups=[("斗鱼合集", assets[0], assets)],
        had_attachments=True,
    )
    assert "info:cloud_quota_soft" not in frame.verdict.tags
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("不合格：待核")


def test_pure_ed2k_quota_mismatch_still_hard():
    """纯 ed2k 标题、链数远少于配额 → 标题偏高软提醒（附件已下）。"""
    title = "合集【10.0g/50V/20配额】"
    sz = int(1024**3)
    a = _ed2k("A" * 32, "a", sz)
    b = _ed2k("B" * 32, "b", sz)
    b.preview_images = []
    parsed = DualParseResult(
        tid=1,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a, b],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("合集", a, [a, b])],
        had_attachments=True,
    )
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert not any("20配额" in e for e in frame.verdict.hard_errors)
