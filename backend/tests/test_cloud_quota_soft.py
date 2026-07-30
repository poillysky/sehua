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
    """纯【115eD2k】且 V≠配额：链数不足 → title_overclaim，勿 cloud_soft。"""
    title = "【整理】【115eD2k】斗鱼合集【194GB/182V/60配额】"
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


def test_quota_echoes_v_requires_capacity_align():
    """182V/182配额 但 xl≪标题容量 → 仍待核（tid=3148293 类，附件未下全）。"""
    title = "【整理】【115eD2k】斗鱼合集【194GB/182V/182配额】"
    sz = int(1024**3)
    assets = [_ed2k(f"{i:032X}", f"v{i}", sz) for i in range(43)]
    for a in assets[1:]:
        a.preview_images = []
    parsed = DualParseResult(
        tid=3148293,
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
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert "info:pack_quota_soft" not in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("不合格：待核"), out


def test_quota_echoes_v_with_capacity_ok():
    """V≈配额且单链 size≈标题容量 → 片数回声，成功（tid=3136385）。"""
    title = "【搬运】【115eD2K】Hamezo 合集【235G/22V/22配额】"
    a = _ed2k("A" * 32, "Hamezo", int(235 * 1024**3))
    parsed = DualParseResult(
        tid=3136385,
        title=title,
        description="【资源大小】：235G/22V/22配额",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("Hamezo", a, [a])],
        had_attachments=True,
    )
    assert "info:pack_quota_soft" in frame.verdict.tags
    assert "info:quota_echoes_v" in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功"), out
    assert not out.startswith("不合格")


def test_quota_over_v_soft_when_links_match_v():
    """2V/3配额 实 2 链：链对齐 V、配额虚高 → 成功+提醒（tid=3137704）。"""
    title = "【自转】【115ed2k】鱼哥新系列【2V/1.45G/3配额】"
    sz = int(0.7 * 1024**3)
    a = _ed2k("A" * 32, "a", sz)
    b = _ed2k("B" * 32, "b", sz)
    b.preview_images = []
    parsed = DualParseResult(
        tid=3137704,
        title=title,
        description="【资源大小】2 V/1.45G",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a, b],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=False,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("鱼哥新系列", a, [a, b])],
    )
    assert "info:quota_over_v_soft" in frame.verdict.tags
    assert "info:pack_quota_soft" in frame.verdict.tags
    out = format_frame_outcome("成功：已提取主链", frame)
    assert out.startswith("成功"), out
    assert not out.startswith("不合格")


def test_pack_title_one_link_quota_soft_success():
    """【115eD2k压缩包】单链 vs N配额 → 成功+提醒，勿待核误杀。"""
    title = "【自录无水印】【115eD2k压缩包】某秀【16V/9.99G/2配额】"
    a = _ed2k("A" * 32, "show", int(9.99 * 1024**3))
    parsed = DualParseResult(
        tid=3273275,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("某秀", a, [a])],
        had_attachments=True,
    )
    assert frame.spec.kind == "single"
    assert "info:pack_quota_soft" in frame.verdict.tags
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功"), out
    assert "提醒:" in out and "配额" in out
    assert not out.startswith("不合格")


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
