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
