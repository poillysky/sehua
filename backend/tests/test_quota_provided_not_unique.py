# -*- coding: utf-8 -*-
"""额度对比：按附件提供链出现次数，不按入库去重 hash（tid=3021466）。"""
from __future__ import annotations

from pathlib import Path

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import (
    build_resource_frame,
    count_post_quota_links,
    count_unique_importable_quota_links,
    format_frame_outcome,
)


def test_duplicate_magnets_count_as_provided_links():
    """75 行 magnet、65 个不重复 hash → 提供数=75，对齐 75配额。"""
    p = Path(r"e:\Downloads\www.98T.la   StayHomePOV.txt")
    if not p.exists():
        # CI 无该文件时用合成样本
        lines = []
        for i in range(65):
            h = f"{i:040X}"
            lines.append(f"magnet:?xt=urn:btih:{h}&dn=")
        # 前 10 个再贴一遍（新的/旧的）
        for i in range(10):
            h = f"{i:040X}"
            lines.append(f"magnet:?xt=urn:btih:{h}&dn=")
        text = "\n".join(lines)
    else:
        text = p.read_bytes().decode("gbk")

    provided = count_post_quota_links(text)
    unique = count_unique_importable_quota_links(text)
    assert provided == 75, provided
    assert unique == 65, unique

    title = "欧美 StayHomePOV【75v/324g/75配额】"
    # 入库仍是去重后的 65 条
    assets = []
    seen: set[str] = set()
    import re

    for h in re.findall(r"btih:([A-Fa-f0-9]{40})", text, re.I):
        hu = h.upper()
        if hu in seen:
            continue
        seen.add(hu)
        assets.append(
            ParsedAsset(
                link_kind="magnet",
                hash=hu,
                filename="StayHomePOV",
                size=0,
                uri=f"magnet:?xt=urn:btih:{hu}&dn=",
                preview_images=["http://a.jpg"] if len(assets) == 0 else [],
                is_primary=len(assets) == 0,
            )
        )
    assert len(assets) == 65

    parsed = DualParseResult(
        tid=3021466,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
        layout="pack_attach_fast",
        had_attachments=True,
        quota_link_count=provided,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("StayHomePOV", assets[0], assets)],
        had_attachments=True,
        layout="pack_attach_fast",
    )
    assert "info:piece_count_match" in frame.verdict.tags
    assert "info:post_links_fill_quota" in frame.verdict.tags
    assert not any("漏链" in w for w in frame.verdict.soft_warnings)
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功"), out
