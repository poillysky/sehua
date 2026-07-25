# -*- coding: utf-8 -*-
from parsers.boards_2048 import is_2048_meta_guide_thread
from workers.thread_outcome import judge_thread_html


def test_meta_guide_title_and_tid():
    assert is_2048_meta_guide_thread("我为人人回家指南&pc安卓地址发布器下载", 13283237)
    assert is_2048_meta_guide_thread(
        "■■■ 来访者必看的内容 - 使你更快速上手 <随时更新> ■■■", 4
    )
    assert is_2048_meta_guide_thread("随便标题", 4)  # 固定 tid
    assert is_2048_meta_guide_thread(
        "在线影片超百万 原档下载 同步更新 高速播放 合集播放", 14022439
    )
    assert not is_2048_meta_guide_thread("★★最新的亚洲无码① / 精彩合集[07.25]", 27434660)
    assert not is_2048_meta_guide_thread("【BT种子】合集", 100)


def test_judge_skips_2048_guide_by_list_title():
    html = (
        "<html><head><title>来访者必看的内容 - 论坛</title></head>"
        "<body><div id='postmessage_1'>版规说明，无磁力</div>"
        + ("<!-- pad -->" * 900)
        + "</body></html>"
    )
    out = judge_thread_html(
        html,
        board_fid="3",
        list_title="■■■ 来访者必看的内容 - 使你更快速上手 <随时更新> ■■■",
        preferred_link="magnet",
        forum_id="2048",
    )
    assert out.verdict == "skipped"
    assert "版务" in out.outcome or "指南" in out.outcome or "广告" in out.outcome


def test_judge_skips_2048_promo_ad_title():
    html = (
        "<html><head><title>在线影片 - 论坛</title></head>"
        "<body><div id='postmessage_1'>广告页无磁力</div>"
        + ("<!-- pad -->" * 900)
        + "</body></html>"
    )
    out = judge_thread_html(
        html,
        board_fid="3",
        list_title="在线影片超百万 原档下载 同步更新 高速播放 合集播放",
        preferred_link="magnet",
        forum_id="2048",
        tid=14022439,
    )
    assert out.verdict == "skipped"
    assert "广告" in out.outcome or "版务" in out.outcome


def test_judge_keeps_2048_resource_title():
    html = (
        "<html><head><title>合集 - 论坛</title></head>"
        "<body><div id='postmessage_1'>"
        "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567"
        "</div>"
        + ("<!-- pad -->" * 900)
        + "</body></html>"
    )
    out = judge_thread_html(
        html,
        board_fid="3",
        list_title="★★最新的亚洲无码① / 精彩合集[07.25]",
        preferred_link="magnet",
        forum_id="2048",
    )
    assert out.verdict == "import"
