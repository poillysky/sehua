# -*- coding: utf-8 -*-
"""Discuz 把【与标签名拆到不同 font 时，须先粘括号再扫子标题（tid=3495371）。"""
from __future__ import annotations

from parsers.content import (
    _glue_structure_brackets_split_by_tags,
    _normalize_structure_brackets_in_scope,
    _repair_missing_structure_open_brackets,
    extract_subresource_blocks_ex,
    iter_subresource_title_spans,
)
from parsers.links import parse_thread_dual


def test_glue_font_split_resource_name():
    raw = '<font size="3">【</font><font size="3">资源名称】：韩漫 傀儡</font>'
    glued = _glue_structure_brackets_split_by_tags(raw)
    assert "【资源名称】" in glued
    # 粘合后开闭之间是纯标签名，不再夹 font
    assert "【资源名称】：韩漫" in glued.replace(" ", "")

def test_normalize_font_split_before_missing_open_repair():
    """先粘再补：避免孤儿【 + 再插【 被跨标签正则误吞。"""
    raw = '<font size="3">【</font><font size="3">资源名称】：韩漫 傀儡</font><br />\n【资源大小】：710M'
    fixed = _normalize_structure_brackets_in_scope(raw)
    titles = iter_subresource_title_spans(fixed)
    assert len(titles) == 1
    assert fixed[titles[0][0] : titles[0][1]] == "【资源名称】"


def test_missing_open_still_works_after_normalize():
    raw = "套图名称】：甘美酱\n【图片数量】：89P\n"
    fixed = _normalize_structure_brackets_in_scope(raw)
    assert fixed.startswith("【套图名称】：")
    # 直接补左【 仍可用
    assert _repair_missing_structure_open_brackets(raw).startswith("【套图名称】：")


def test_font_split_name_two_ed2k_is_single_resource():
    """一楼【资源名称】被 font 拆开 + pdf/rar 双链 → 单资源多链接，勿 no_subtitle。"""
    html = """
    <div id="postmessage_1" class="t_f">
    <font size="3">【</font><font size="3">资源名称】：韩漫 傀儡</font><br />
    <font size="3">【资源类型】：动漫</font><br />
    <font size="3">【资源大小】：710M</font><br />
    ed2k://|file|a.pdf|389751376|42C772D007BDEECEB7F099474EDBDD37|/<br />
    ed2k://|file|a.rar|355261006|D98DDE73D6A19AF1DDC21AFB06E1D781|/<br />
    </div>
    """
    title = "【自转】【115eD2k】韩漫补全【710M/1pdf、1rar/2配额】"
    blocks, layout = extract_subresource_blocks_ex(
        html, fallback_title=title, board_fid="95"
    )
    assert layout != "no_subtitle"
    assert len(blocks) >= 1
    # 同名双链应并在一块或两块同名；不应出现整帖标题当第二资源名
    names = {b.title for b in blocks}
    assert any("傀儡" in (n or "") for n in names)
    assert title not in names

    dual = parse_thread_dual(
        html,
        tid=3495371,
        preferred_link="ed2k",
        board_fid="95",
    )
    assert dual.layout != "no_subtitle"
    filenames = [(a.filename or "") for a in dual.assets]
    assert any("傀儡" in f for f in filenames)
    assert not any(f == title for f in filenames)
