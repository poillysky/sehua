# -*- coding: utf-8 -*-
"""标题配额优先于描述脏配额（tid=3437461）。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def _ed2k(h: str, name: str, size: int) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}|{size}|{h}|/",
        preview_images=["http://a.jpg"] if h.startswith("A") else [],
    )


def test_title_quota_beats_desc_dirty_quota():
    """标题 6配额 + 正文 6 链；描述【资源大小】8配额不得抬成期望 8。"""
    title = "【整理】【115ed2k】amazona 合集【6v/173MB/6配额】"
    desc = (
        "【资源名称】：" + title + "\n"
        "【资源大小】：8v/314MB/8配额\n"
    )
    sz = 20 * 1024 * 1024
    assets = [
        _ed2k((f"{i:032X}"), f"v{i}.mp4", sz) for i in range(6)
    ]
    assets[0].preview_images = ["http://a.jpg"]
    parsed = DualParseResult(
        tid=3437461,
        title=title,
        description=desc,
        metadata={"资源大小": "8v/314MB/8配额"},
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
    )
    assert frame.verdict.metrics.get("title_piece_expect") == 6
    assert frame.verdict.metrics.get("title_quota_count") == 6
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    out = format_frame_outcome("成功：正文含目标链接", frame)
    assert out.startswith("成功")
    assert not out.startswith("不合格")
