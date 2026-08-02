# -*- coding: utf-8 -*-
"""额度对比：按附件提供链出现次数，不按入库去重 hash（tid=3021466）。"""
from __future__ import annotations

from pathlib import Path

from db.persist import preview_frame_outcome
from parsers.attachments import inject_attachment_text
from parsers.links import DualParseResult, ParsedAsset, parse_thread_dual
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


def test_broken_ed2k_lines_count_for_quota_not_import():
    """额度计全部 ed2k:// 行（含残缺 hash）；入库只收合法链（tid=2623349）。

    pipeline 常 inject 后不传 extra_text——额度须从 postmessage_attach 回取。
    """
    good = (
        "ed2k://|file|a.mp4|100|D8B324C10A02F349611B0FC7879074CD|/\n"
        "ed2k://|file|b.mp4|200|9F4EBABCDEF0123456789ABCDEF01234|/\n"
        "ed2k://|file|c.mp4|300|CE45834334EABC5B79BC398668273D09|/\n"
    )
    # 5 行残缺（无完整 32 hex），仍算提供链
    broken = (
        "ed2k://|file|d.mp4|400|9F4EB\n"
        "ed2k://|file|e.mp4|500|7D588\n"
        "ed2k://|file|f.mp4|600|70717\n"
        "ed2k://|file|g.mp4|700|799AFD6F\n"
        "ed2k://|file|h.mp4|800|0976DF0\n"
    )
    attach = good + broken
    assert count_post_quota_links(attach) == 8

    html = (
        '<html><body><span id="thread_subject">'
        "【115eD2K】合集【8V/10GB/8配额】</span>"
        '<div id="postmessage_1">【影片名称】合集包</div></body></html>'
    )
    # 模拟 pipeline：只 inject、不传 extra_text
    html2 = inject_attachment_text(html, attach)
    parsed = parse_thread_dual(
        html2, tid=2623349, preferred_link="ed2k", extra_text="", board_fid="141:844"
    )
    parsed.had_attachments = True
    assert parsed.quota_link_count == 8, parsed.quota_link_count
    assert len(parsed.assets) == 3  # 仅合法 32 位 hash
    out = preview_frame_outcome(
        parsed,
        import_outcome="成功：附件解析出目标链接",
        post_title=parsed.title or "",
    )
    assert out.startswith("成功"), out
    assert "漏链" not in out
