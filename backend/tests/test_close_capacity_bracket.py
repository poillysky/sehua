# -*- coding: utf-8 -*-
"""未闭合容量括号自动补】。"""
from parsers.content import extract_title
from parsers.thread_gates import close_trailing_capacity_bracket, title_looks_list_truncated


def test_close_trailing_quota_bracket():
    raw = "【自转】【ED2K】✅酒店精品✅性感白袜女孩摸鸡后被操【5V/2.49GB/5配额"
    assert close_trailing_capacity_bracket(raw).endswith("5配额】")
    assert close_trailing_capacity_bracket(raw) == raw + "】"


def test_close_trailing_size_unit_bracket():
    raw = "合集标题【1.02g/21p+ 37v"
    assert close_trailing_capacity_bracket(raw).endswith("37v】")


def test_no_close_non_capacity_open_bracket():
    raw = "SIRO-4387 【初次摄影】【停不下来的潮吹】【苗条细腰"
    assert close_trailing_capacity_bracket(raw) == raw


def test_already_closed_unchanged():
    raw = "合集【8V/2配额】"
    assert close_trailing_capacity_bracket(raw) == raw


def test_extract_title_closes_quota():
    html = """
    <span id="thread_subject">【自转】【115ed2k】超级美少女【2V/2G/2配额</span>
    """
    t = extract_title(html)
    assert t.endswith("2配额】")
    assert not title_looks_list_truncated(t)
