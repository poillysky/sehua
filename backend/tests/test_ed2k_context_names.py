"""ed2k 旁【影片名称】/【资源名称】作为 display_name，链内名保留在 URI。"""

from __future__ import annotations

from parsers.ed2k import parse_ed2k_text
from parsers.links import build_assets


def test_ed2k_context_display_name():
    text = """
    ed2k://|file|pack-inner.rar|100|AAAABBBBCCCCDDDDEEEEFFFF00001111|/
    【资源名称】: 综合真名甲
    ed2k://|file|other.bin|200|BBBBCCCCDDDDEEEEFFFF000011112222|/
    【资源名称】: 综合真名乙
    """
    links = parse_ed2k_text(text)
    assert len(links) == 2
    assert links[0].filename == "pack-inner.rar"
    assert links[0].display_name == "综合真名甲"
    assert "pack-inner.rar" in links[0].link
    assert links[1].display_name == "综合真名乙"

    assets, _ = build_assets([], links, preferred="ed2k")
    assert assets[0].filename == "综合真名甲"
    assert assets[1].filename == "综合真名乙"


def test_ed2k_without_label_asset_filename_empty():
    text = "ed2k://|file|only-link.mp4|9|CCCCCCCCDDDDDEEEEEFFFFF000011112|/"
    links = parse_ed2k_text(text)
    assert links[0].filename == "only-link.mp4"
    assert links[0].display_name == ""
    assets, _ = build_assets([], links, preferred="ed2k")
    assert assets[0].filename == ""


def test_glued_ed2k_missing_pipes_from_2048_txt():
    """2048 附件 txt：扩展名、大小、hash 粘连无 |（tid=27424341）。"""
    text = (
        "ed2k://|file|www.98T.la@AMBI-039.mp4206253751428B6B31078561A2E8E749E819E957421\n"
        "ed2k://|file|www.98T.la@ARM-344.mp41377073636F8D10C23B79C1F49E606D5B8B111F4C4\n"
    )
    links = parse_ed2k_text(text)
    assert len(links) == 2
    assert links[0].filename == "www.98T.la@AMBI-039.mp4"
    assert links[0].size == 2062537514
    assert links[0].hash == "28B6B31078561A2E8E749E819E957421"
    assert "|2062537514|" in links[0].link
    assert links[1].filename.endswith(".mp4")
    assert links[1].size == 1377073636


def test_txt_dirty_paragraph_then_ed2k_all_recognized():
    """附件 txt：脏段/广告后仍有完整 ed2k，必须认全（可多段）。"""
    h1 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    h2 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    text = (
        "百度网盘链接: https://pan.baidu.com/s/1abcd 提取码: xy12\n"
        "本资源仅供学习，请勿传播。密码错误请重试。\n"
        "\n"
        f"ed2k://|file|www.98T.la@part1.mp4|111111|{h1}|/\n"
        "\n"
        "==== 分隔 / 更多广告 ====\n"
        "夸克网盘口令无效 某某推广￥12\n"
        "\n"
        f"ed2k://|file|www.98T.la@part2.mp4|222222|{h2}|/\n"
    )
    links = parse_ed2k_text(text)
    assert len(links) == 2
    assert {x.hash for x in links} == {h1, h2}
    assert all("98T.la" in x.filename for x in links)


def test_txt_broken_ed2k_prefix_does_not_swallow_next():
    """半截/脏 ed2k 不得把后面完整链的 size|hash 吞进前一条。"""
    h = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
    text = (
        "ed2k://|file|broken.mp4|notanumber|notahash|\n"
        "\n"
        f"ed2k://|file|good.mp4|444|{h}|/\n"
    )
    links = parse_ed2k_text(text)
    assert len(links) == 1
    assert links[0].filename == "good.mp4"
    assert links[0].hash == h
    assert links[0].size == 444
