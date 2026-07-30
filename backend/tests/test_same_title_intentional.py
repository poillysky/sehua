# -*- coding: utf-8 -*-
"""套图名称缺左【 / 子名=帖标题误判。"""
from __future__ import annotations

from parsers.content import _repair_missing_structure_open_brackets, extract_subresource_blocks
from parsers.links import DualParseResult, ParsedAsset, parse_thread_dual
from parsers.resource_frame import build_resource_frame, format_frame_outcome


def _asset(h: str, name: str, *, size: int = 0, desc: str = "") -> ParsedAsset:
    a = ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename=name,
        size=size,
        uri="magnet:?xt=urn:btih:" + h,
        preview_images=["http://x/1.jpg"],
    )
    if desc:
        a.description = desc
    return a


def test_repair_missing_open_bracket_taotu():
    raw = "套图名称】：甘美酱 诱人酮体[89P/236M]\n【图片数量】：89P\n"
    fixed = _repair_missing_structure_open_brackets(raw)
    assert fixed.startswith("【套图名称】：")


def test_taotu_missing_bracket_gets_first_name():
    html = """
    <div id="read_tpc">
    套图名称】：甘美酱 诱人酮体[89P/236M]<br>
    【图片数量】：89P<br>
    【文件大小】：236M<br>
    【磁力连接】：magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA<br>
    【套图名称】：刘震撼 迷人的眼神[178P/569M]<br>
    【图片数量】：178P<br>
    【文件大小】：569M<br>
    【磁力连接】：magnet:?xt=urn:btih:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB<br>
    </div>
    """
    title = "★◇精彩の套图写真㊣↗精品合集↘♀ [02.08]"
    blocks = extract_subresource_blocks(html, fallback_title=title)
    assert len(blocks) >= 2
    assert "甘美" in blocks[0].title
    assert blocks[0].title != title
    dual = parse_thread_dual(html, tid=24506022, preferred_link="magnet", board_fid="2048")
    assert "甘美" in (dual.assets[0].filename or "")


def test_first_film_same_as_subject_not_hard_fail():
    """帖主用首片当标题：有容量文案则不报漏识别（tid=22334497）。"""
    title = "新人超骚美少妇下海夜色妩媚毛坯房内无套啪啪大秀爽清秀白皙花式操穴"
    a = _asset(
        "A" * 40,
        title,
        size=4524 * 1024**2,
        desc=f"【影片名称】：{title}\n【影片大小】：4524 MB\n【影片格式】：MP4",
    )
    b = _asset(
        "B" * 40,
        "另一条资源名测试用",
        size=100 * 1024**2,
        desc="【影片名称】：另一条资源名测试用\n【影片大小】：100 MB\n【影片格式】：MP4",
    )
    parsed = DualParseResult(
        tid=22334497,
        title=title,
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=[a, b],
        primary_link_kind="magnet",
        layout="title_then_magnet",
        had_attachments=False,
    )
    groups = [(a.filename, a, [a]), (b.filename, b, [b])]
    frame = build_resource_frame(parsed, named_groups=groups, layout="title_then_magnet")
    assert not any("等于帖标题" in e for e in frame.verdict.hard_errors)
    assert not any("过短或占位" in e for e in frame.verdict.hard_errors)
    out = format_frame_outcome("已提取", frame)
    assert out.startswith("成功")
