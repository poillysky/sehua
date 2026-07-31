# -*- coding: utf-8 -*-
"""配额对齐：帖内链接总数即可，不必都是可入库有效链。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import (
    build_resource_frame,
    count_http_host_media_links,
    count_post_quota_links,
    format_frame_outcome,
)


def _ed2k(h: str, name: str, size: int) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}|{size}|{h}|/",
        preview_images=["http://a.jpg"],
    )


def test_count_http_host_media_links():
    blob = (
        "ed2k://|file|a.mp4|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/\n"
        "http://107.151.184.2/y/a1080hd.com@jul00067hhb.ffqr9igb.mp4\n"
        "http://69.197.132.50/y/jul00173hhb.g3z312j7.mp4,"
        "http://69.197.132.50/y/jul00221hhb.xg254qpd.mp4\n"
    )
    assert count_http_host_media_links(blob) == 3
    # 帖内总数：1 ed2k + 3 http
    assert count_post_quota_links(blob) == 4


def test_html_href_and_text_not_double_counted():
    """Discuz ``<a href=ed2k>ed2k</a>``：额度按出现次数，但同一锚点 href+文字只计 1。"""
    u1 = "ed2k://|file|a1.rar|1|DEA33131F76ECF406DC869805FD50B8B|/"
    u2 = "ed2k://|file|a2.rar|2|0F6A83BE78184FE1784F3AB25AE64DF6|/"
    html = f'<a href="{u1}">{u1}</a>\n<a href="{u2}">{u2}</a>'
    assert count_post_quota_links(html) == 2
    # 可见区同链贴两行 → 不去重，算 2
    plain_dup = f"{u1}\n{u1}"
    assert count_post_quota_links(plain_dup) == 2
    # 叠语料（抽链用）若误传入仍会偏高——调用方应单源；此处仅文档化风险
    stacked = html + "\n" + u1 + "\n" + u2
    assert count_post_quota_links(stacked) >= 2


def test_plain_text_duplicate_lines_still_count_occurrences():
    """附件 txt 同链贴多行仍按出现次数（对齐 N配额），勿按 hash 去重。"""
    h = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    line = f"magnet:?xt=urn:btih:{h}&dn=x"
    blob = "\n".join([line] * 5)
    assert count_post_quota_links(blob) == 5
    assert "<" not in blob


def test_href_only_anchor_still_counts():
    """锚点文字不是链、链只在 href 时仍要计入提供数。"""
    u = "ed2k://|file|a.rar|1|DEA33131F76ECF406DC869805FD50B8B|/"
    html = f'<a href="{u}">点击下载</a>'
    assert count_post_quota_links(html) == 1


def test_post_links_fill_quota_without_all_importable():
    """42 可入库 + 帖内共 56 链 ≈ 57配额（V≠配额）→ 对齐，勿待核。"""
    title = "【整理】【115ED2K】【原档】熟女系列【260.29GB/120V/57配额】"
    assets = [_ed2k(f"{i:032X}", f"v{i}.mp4", int(1024**3)) for i in range(42)]
    for a in assets[1:]:
        a.preview_images = []
    parsed = DualParseResult(
        tid=3171127,
        title=title,
        description="",
        metadata={},
        preview_images=["http://a.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="ed2k",
        layout="",
        had_attachments=True,
        quota_link_count=56,
        http_media_count=14,
    )
    frame = build_resource_frame(
        parsed,
        named_groups=[("熟女系列", assets[0], assets)],
        had_attachments=True,
    )
    assert "info:piece_count_match" in frame.verdict.tags
    assert "info:post_links_fill_quota" in frame.verdict.tags
    assert not any("漏链" in w for w in frame.verdict.soft_warnings)
    out = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert out.startswith("成功"), out


def test_broken_ed2k_still_counts_for_quota():
    """残缺 ed2k 也算帖内链，不必解析成功。"""
    blob = (
        "ed2k://|file|broken.mp4|123|DEADBEEF|/\n"  # hash 过短，通常不可入库
        "ed2k://|file|ok.mp4|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/\n"
        "http://1.2.3.4/y/x.mp4\n"
    )
    assert count_post_quota_links(blob) == 3
