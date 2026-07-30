# -*- coding: utf-8 -*-
"""帖标题内嵌【影片名称】时还原片名（tid=1475266 / 2156323）。"""
from __future__ import annotations

from parsers.content import extract_title
from parsers.links import parse_thread_dual
from parsers.resource_names import unwrap_subject_film_title


def test_unwrap_subject_film_title_with_board_letter():
    raw = (
        "B 【影片名称】：7月份新星，【极品御姐】【小土软乎乎】小合集，闷骚清纯，玩道具，"
        "微微张开的小阴穴，水汩汩溢出 【出演女优】：极品御姐 【影片容量】：3.41G 【是否有码】：无码 【..."
    )
    got = unwrap_subject_film_title(raw)
    assert got.startswith("7月份新星")
    assert "出演女优" not in got
    assert "影片容量" not in got
    assert not got.startswith("B")
    assert "极品御姐" in got  # 装饰括号保留在片名里


def test_unwrap_subject_film_title_plain_label():
    raw = "【影片名称】：真实良家偷拍，【推油少年】，女大学生，漂亮露脸"
    got = unwrap_subject_film_title(raw)
    assert got.startswith("真实良家偷拍")
    assert not got.startswith("【影片名称】")


def test_unwrap_leaves_normal_title():
    assert unwrap_subject_film_title("【整理】【115eD2k】合集【22V/22配额】") == (
        "【整理】【115eD2k】合集【22V/22配额】"
    )
    # 无影片名称标签时，不剥前导字母
    assert unwrap_subject_film_title("B 普通讨论帖") == "B 普通讨论帖"


def test_extract_title_unwraps_film_name_label():
    """标题剥 B 【影片名称】：，其余按页面原文。"""
    html = """
    <html><body>
    <span id="thread_subject">B 【影片名称】：7月份新星，【极品御姐】小合集 【出演女优】：极品御姐 【影片容量】：3.41G</span>
    <div id="postmessage_1">
    【出演女优】：极品御姐<br/>
    【影片容量】：3.41G<br/>
    magnet:?xt=urn:btih:52DFB5094D81EEC1B25A74487AC8D462721B1C11
    </div>
    </body></html>
    """
    title = extract_title(html)
    assert title.startswith("7月份新星")
    assert not title.startswith("B")
    assert "【影片名称】" not in title
    assert "出演女优" not in title
    dual = parse_thread_dual(html, tid=1475266, preferred_link="magnet")
    assert dual.title.startswith("7月份新星")


def test_extract_title_unwraps_plain_film_label():
    html = """
    <html><body>
    <span id="thread_subject">【影片名称】：真实良家偷拍，【推油少年】，女大学生</span>
    <div id="postmessage_1">
    【影片容量】：677M<br/>
    magnet:?xt=urn:btih:E094BEEED192D114549DEE98D64BE82880D14855
    </div>
    </body></html>
    """
    title = extract_title(html)
    assert title.startswith("真实良家偷拍")
    assert not title.startswith("【影片名称】")
    dual = parse_thread_dual(html, tid=2156323, preferred_link="magnet")
    assert dual.title.startswith("真实良家偷拍")
