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
