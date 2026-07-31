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


def test_attach_filename_v_sum_matches_links_not_review():
    """全部可用附件名 Nv 合计=实链；标题更高配额 → 按附件合计对齐，勿待核。

    tid=2178766：标题 589配额，主附件 96v，实链 96（备用/封面不计 Nv）。
    """
    title = "【自整理】【磁力】Emily.Thorne【589v/577g/589配额】"
    sz = 10 * 1024 * 1024
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash=f"{i:040X}",
            filename=title,
            size=sz,
            uri=f"magnet:?xt=urn:btih:{i:040x}",
            preview_images=["http://a.jpg"] if i == 0 else [],
        )
        for i in range(96)
    ]
    parsed = DualParseResult(
        tid=2178766,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
        layout="pack_attach_fast",
        had_attachments=True,
        attachment_names=[
            "www.98T.la  Emily.Thorne  备用链接，离线失败.txt",
            "封面女优.txt",
            "www.98T.la  Emily.Thorne  96v .txt",
        ],
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, assets[0], assets)],
        had_attachments=True,
    )
    assert frame.verdict.metrics.get("attach_filename_v_sum") == 96
    assert "info:attach_filename_v_match" in frame.verdict.tags
    assert "info:piece_count_match" in frame.verdict.tags
    assert "info:pack_quota_soft" in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功")
    assert "不合格：待核" not in out


def test_attach_filename_v_sum_short_of_links_is_review():
    """附件名合计 100，实得仅 40 → 漏下分卷，待核。"""
    title = "合集【100配额】"
    sz = 10 * 1024 * 1024
    assets = [
        _ed2k(f"{i:032X}", f"v{i}.mp4", sz, prev=(i == 0)) for i in range(40)
    ]
    parsed = DualParseResult(
        tid=2,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="ed2k",
        layout="pack_attach_fast",
        had_attachments=True,
        attachment_names=["A 60v.txt", "B 40v.txt"],
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, assets[0], assets)],
        had_attachments=True,
    )
    assert frame.verdict.metrics.get("attach_filename_v_sum") == 100
    assert "info:attach_links_short_of_filename_v" in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("不合格：待核")
    assert any("附件文件名合计" in w or "附件名合计" in w for w in frame.verdict.soft_warnings)


def test_product_code_v_not_quota_review():
    """番号 START-600V 不是片数 Nv；无配额时额度对照跳过（tid=3640451）。"""
    from parsers.resource_frame import _attach_filename_v_sum, _title_v_count

    title = "START-600V [无码破解] 【特典版】夏目響 引退"
    assert _title_v_count(title) is None
    assert _attach_filename_v_sum([f"{title}.txt", "START-600V.torrent"]) is None

    sz = 2 * 1024 * 1024 * 1024
    asset = _ed2k("A" * 32, f"{title}.mp4", sz, prev=True)
    parsed = DualParseResult(
        tid=3640451,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[asset],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
        attachment_names=[f"{title}.txt"],
        quota_link_count=1,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, asset, [asset])],
        had_attachments=True,
    )
    assert frame.verdict.metrics.get("attach_filename_v_sum") in (None, 0)
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:attach_links_short_of_filename_v" not in frame.verdict.tags
    out = format_frame_outcome("成功：正文含目标链接", frame)
    assert out.startswith("成功")
    assert "不合格：待核" not in out


def test_attach_v_without_quota_does_not_review():
    """无标题配额时，附件名 Nv 短于链数也不作额度待核。"""
    title = "某合集无配额字样"
    sz = 10 * 1024 * 1024
    assets = [
        _ed2k(f"{i:032X}", f"v{i}.mp4", sz, prev=(i == 0)) for i in range(3)
    ]
    parsed = DualParseResult(
        tid=3,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="ed2k",
        layout="pack_attach_fast",
        had_attachments=True,
        attachment_names=["合集 100v.txt"],
        quota_link_count=3,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[(title, assets[0], assets)],
        had_attachments=True,
    )
    assert frame.verdict.metrics.get("attach_filename_v_sum") == 100
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:attach_links_short_of_filename_v" not in frame.verdict.tags
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功")
