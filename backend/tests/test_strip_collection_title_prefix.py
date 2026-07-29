# -*- coding: utf-8 -*-
"""不再砍帖标题前缀：资源名保留原文。"""
from __future__ import annotations

from parsers.content import (
    _drop_thread_title_lines,
    _subresource_title_value,
    extract_subresource_blocks,
)
from parsers.resource_names import is_weak_subresource_name


def test_drop_thread_title_keeps_full_name():
    """产品口径：资源名是什么就显示什么，不再剥帖标题前缀。"""
    title = "★★最强優片★★最強國產專輯A♂[05.31]"
    raw = f"{title}\n19岁宿舍学生妹06小烤肠下海福利"
    got = _drop_thread_title_lines(raw, title)
    assert "最强優片" in got and "19岁" in got

    raw2 = f"{title} 19岁宿舍学生妹06小烤肠下海福利"
    got2 = _drop_thread_title_lines(raw2, title)
    assert "最强優片" in got2 and "19岁" in got2


def test_drop_keeps_title_plus_comma_tail():
    title = (
        "2025年X月最新，【PANS重磅】，极品气质模特，【希希】，"
        "颜值最高，女神绝美，大尺度直接露点露穴"
    )
    raw = title + "，好大方"
    got = _drop_thread_title_lines(raw, title)
    assert got == raw
    assert got.startswith("2025")
    assert "好大方" in got


def test_subresource_title_value_keeps_pasted_header():
    """粘贴的合集头+真名整段保留。"""
    title = "★★最强優片★★最強國產專輯A♂[05.31]"
    scope = (
        f"【影片标题】：{title}<br/>"
        "19岁宿舍学生妹06小烤肠下海福利，特写超粉嫩的小穴自慰诱惑<br/>"
        "【影片格式】：MP4<br/>"
        "【影片标题】：下一条"
    )
    import re

    m = re.search(r"【影片标题】", scope)
    assert m
    t_end = m.end()
    next_start = scope.index("【影片标题】", t_end)
    name = _subresource_title_value(
        scope, t_end, next_start, label_start=m.start(), thread_title=title
    )
    assert "19岁" in name
    # 不再强制去掉合集头
    assert len(name) >= 10


def test_film_title_is_post_title_use_torrent_name():
    """tid=23485940：首条【影片标题】=帖标题（空格差），真名在【种子名称】。"""
    title = "★★最强優片★★最強國產專輯A♂[12.27 ]"
    assert is_weak_subresource_name(
        "★★最强優片★★最強國產專輯A♂[12.27]", post_title=title
    )
    html = f"""
    <div id="read_tpc">
    【影片标题】：★★最强優片★★最強國產專輯A♂[12.27 ]<br>
    【影片格式】：MP4<br>
    【影片大小】：560 MB<br>
    【驗證編號】：7DCDDFDD7B8DCD8A630E79A9BAD347280F3D02B1<br>
    【种子名称】： 《用利抽插》约操肉感小少妇按着头深喉口交.torrent<br>
    【磁力连接】： magnet:?xt=urn:btih:7DCDDFDD7B8DCD8A630E79A9BAD347280F3D02B1<br>
    【影片标题】：【666小祁探花】门票188极品外围<br>
    【影片格式】：MP4<br>
    【影片大小】：3343 MB<br>
    【驗證編號】：D589D915FEC2DF35CBC4BB4137544307DAAFAEDA<br>
    【种子名称】： 【666小祁探花】门票188极品外围.torrent<br>
    【磁力连接】： magnet:?xt=urn:btih:D589D915FEC2DF35CBC4BB4137544307DAAFAEDA<br>
    </div>
    """
    blocks = extract_subresource_blocks(html, fallback_title=title)
    assert len(blocks) >= 2
    assert "用利抽插" in blocks[0].title
    assert "最强優片" not in blocks[0].title
    assert "666小祁探花" in blocks[1].title


def test_album_header_when_subject_is_film_name():
    """tid=23486061：subject=单片名，首条【影片标题】仍是专辑头 → 帖标题恢复专辑头，子名用种子名。"""
    from parsers.content import extract_title
    from parsers.links import parse_thread_dual

    album = "★★最强優片★★最強歐美專輯♂[12.27 ]"
    html = f"""
    <html><head><title>All Over Your Body | 最新合集 - 论坛</title></head>
    <body>
    <h1 id="subject_tpc">All Over Your Body</h1>
    <div id="read_tpc">
    【影片标题】{album}<br>
    【影片格式】：MP4<br>
    【影片大小】：815 MB<br>
    【驗證編號】：7F464F12DCE5B99161AF0FA55E99E2BEB52C384D<br>
    【种子名称】： A Dress Fit For Fucking.torrent<br>
    【磁力连接】： magnet:?xt=urn:btih:7F464F12DCE5B99161AF0FA55E99E2BEB52C384D<br>
    A Dress Fit For Fucking<br>
    【影片标题】：All Over Your Body<br>
    【影片格式】：MP4<br>
    【影片大小】：700 MB<br>
    【驗證編號】：AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA<br>
    【种子名称】： All Over Your Body.torrent<br>
    【磁力连接】： magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA<br>
    </div>
    </body></html>
    """
    assert "最强優片" in extract_title(html)
    dual = parse_thread_dual(html, tid=23486061, preferred_link="magnet", board_fid="2048")
    assert "最强優片" in (dual.title or "")
    assert "A Dress Fit For Fucking" in (dual.assets[0].filename or "")
    assert dual.assets[0].filename != dual.title
