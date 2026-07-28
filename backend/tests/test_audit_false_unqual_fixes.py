# -*- coding: utf-8 -*-
"""标题无配额时勿吃描述脏配额；磁力 URI/hash 勿双计。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.magnet import MagnetLink
from parsers.resource_frame import (
    FrameRow,
    FrameSpec,
    ResourceFrame,
    SlotFill,
    _recog_link_keys,
    build_resource_frame,
    format_frame_outcome,
    validate_frame,
)


def _ed2k(h: str, name: str, size: int) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}|{size}|{h}|/",
        preview_images=["http://a.jpg"] if h.startswith("A") else [],
    )


def test_title_without_quota_ignores_desc_dirty_quota():
    """标题仅【198M/1V】无配额字样；描述脏 2配额不得抬期望（tid=3613140）。"""
    title = "【自转】【115ED2k】【AI视频】短剧【198M/1V】"
    desc = (
        "【资源名称】：短剧\n"
        "【资源大小】：198M/2V/2配额\n"
        "【资源类型】：视频\n"
    )
    a = _ed2k("A" * 32, "短剧", 198 * 1024 * 1024)
    a.preview_images = ["http://a.jpg"]
    parsed = DualParseResult(
        tid=3613140,
        title=title,
        description=desc,
        metadata={"资源大小": "198M/2V/2配额"},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=[a],
        primary_link_kind="ed2k",
        layout="title_then_magnet",
    )
    frame = build_resource_frame(parsed, named_groups=[("短剧", a, [a])])
    assert frame.verdict.metrics.get("title_piece_expect") is None
    assert frame.verdict.metrics.get("title_quota_count") is None
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:title_quota_overclaim_soft" not in frame.verdict.tags
    out = format_frame_outcome("成功：正文含目标链接", frame)
    assert out.startswith("成功")
    assert "2配额" not in out


def test_magnet_uri_and_infohash_not_double_counted():
    """asset.magnet URI + magnets[].infohash 不得算成识别 2 入库 1。"""
    h = "8428C99580F959F3E78B3A75629D5E0F54B1F0AE"
    uri = f"magnet:?xt=urn:btih:{h}"
    asset = ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename="demo",
        size=0,
        uri=uri,
        preview_images=["http://a.jpg"],
    )
    parsed = DualParseResult(
        tid=3495608,
        title="demo",
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        magnets=[MagnetLink(infohash=h, filename="demo", size=0, link=uri)],
        assets=[asset],
        primary_link_kind="magnet",
    )
    recog = _recog_link_keys(parsed, {"magnet"})
    assert len(recog) == 1
    assert h in recog

    row = FrameRow(
        filename="demo",
        size=0,
        previews=["http://a.jpg"],
        links=[uri],
        hashes=[h],
        head=asset,
        members=[asset],
        slots=[
            SlotFill("filename", True, "demo"),
            SlotFill("links", True, "1"),
            SlotFill("previews", True, "1"),
            SlotFill("size", False, "0"),
        ],
    )
    spec = FrameSpec(shape="A", kind="single", capacity="ok", source="body", layout="")
    verdict = validate_frame(spec, [row], parsed, post_title="demo")
    assert "warn:link_sum_mismatch" not in verdict.tags
    assert verdict.metrics.get("recog_links") == 1
    frame = ResourceFrame(spec=spec, rows=[row], verdict=verdict)
    out = format_frame_outcome("成功：已提取主链", frame)
    assert out.startswith("成功")
    assert "≠识别" not in out
