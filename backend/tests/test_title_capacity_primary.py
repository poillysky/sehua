# -*- coding: utf-8 -*-
"""标题容量优先于描述脏【资源大小】（tid=2829365）。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def test_title_capacity_beats_desc_dirty_size():
    title = "【115ed2k】Dirty-Coach 合集【35V/31G/35配额】"
    desc = (
        "【资源名称】：Dirty-Coach 合集【35V/31G/35配额】\n"
        "【资源大小】：51V/11G/51配额\n"
    )
    sz = int(31 * 1024**3)
    # 32 链合计约 31G（与标题对齐）
    per = sz // 32
    assets = [
        ParsedAsset(
            link_kind="ed2k",
            hash=f"{i:032X}",
            filename=f"v{i}.mp4",
            size=per,
            uri=f"ed2k://|file|v{i}.mp4|{per}|{i:032X}|/",
            preview_images=["http://a.jpg"] if i == 0 else [],
        )
        for i in range(32)
    ]
    parsed = DualParseResult(
        tid=2829365,
        title=title,
        description=desc,
        metadata={"资源大小": "51V/11G/51配额"},
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
    assert frame.verdict.status == "ok"
    assert not any("容量不合规" in e for e in frame.verdict.hard_errors)
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert not out.startswith("不合格")
