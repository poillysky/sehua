# -*- coding: utf-8 -*-
"""短目录号种子名 / [分类] 目录行命名（tid=27377735）。"""

from parsers.content import (
    _is_bogus_meta_value,
    _title_from_catalog_bracket_line,
    _torrent_name_as_title,
    extract_subresource_blocks_ex,
)


def test_short_catalog_torrent_name_not_bogus():
    """OM1/OM9 长度<4 不得当残片丢掉（否则只剩 OM10+）。"""
    assert _is_bogus_meta_value("种子名称", "OM1") is False
    assert _is_bogus_meta_value("种子名称", "OM9") is False
    assert _is_bogus_meta_value("种子名称", "JP3") is False
    assert _torrent_name_as_title("OM1.torrent") == "OM1"
    assert _torrent_name_as_title("OM9.torrent") == "OM9"
    assert _torrent_name_as_title("OM10.torrent") == "OM10"
    # 仍丢真正残片
    assert _is_bogus_meta_value("种子名称", "]ent") is True
    assert _is_bogus_meta_value("种子名称", "ab") is True


def test_catalog_bracket_line_title():
    chunk = (
        "[欧美无码] OM1 AccidentalGangbang.24.06.20.XXX.720p[XvX]\n"
        "【影片格式】：MP4\n"
        "【种子名称】：OM1.torrent\n"
    )
    assert _title_from_catalog_bracket_line(chunk).startswith("OM1 Accidental")


def test_catalog_bracket_hat_long_digits():
    """HAT13057 五位数字目录号（tid=25026517 空壳条目后）。"""
    chunk = (
        "[动漫精品] HAT13056\n"
        "【种子名称】：\n"
        "【磁力连接】：\n"
        "[动漫精品] HAT13057 [基德漠化组] 迷情 第二季\n"
        "【种子名称】：HAT13057.torrent\n"
    )
    assert "HAT13057" in _title_from_catalog_bracket_line(chunk, prefer_last=True)
    assert _torrent_name_as_title("HAT13057.torrent") == "HAT13057"


def test_empty_stub_seed_prefer_last_torrent():
    from parsers.content import TORRENT_FIELD_FORMS, _block_field

    chunk = (
        "【种子名称】： 【磁力连接】：\n"
        "【种子名称】：HAT13057.torrent\n"
        "【磁力连接】：\n"
    )
    # 跳过空壳，取首个可用
    assert _block_field(chunk, *TORRENT_FIELD_FORMS) == "HAT13057.torrent"


def test_catalog_bracket_numeric_index_title():
    """[欧美无码] 01 18Lust... 不得只吃到种子名 01（tid=27191175）。"""
    chunk = (
        "[欧美无码] 01 18Lust.24.06.19.Juliette.Fucks.Till.Orgasm.XXX.720p[XvX]\n"
        "【影片格式】：MP4\n"
        "【种子名称】：01.torrent\n"
    )
    got = _title_from_catalog_bracket_line(chunk)
    assert got.startswith("01 18Lust")
    assert "Juliette" in got


def test_no_subtitle_om_catalog_splits_all():
    """无【影片名称】时，按 [分类]+种子名 切出 OM1..OM3，勿回落帖标题。"""
    scope = """
[欧美无码] OM1 Foo.Bar.XXX
【影片格式】：MP4
【种子名称】：OM1.torrent
magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
-----------------------------------
[欧美无码] OM2 Baz.Qux.XXX
【影片格式】：MP4
【种子名称】：OM2.torrent
magnet:?xt=urn:btih:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
-----------------------------------
[欧美无码] OM10 Long.Name.XXX
【影片格式】：MP4
【种子名称】：OM10.torrent
magnet:?xt=urn:btih:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
"""
    hashes = [
        "A" * 40,
        "B" * 40,
        "C" * 40,
    ]
    blocks, layout = extract_subresource_blocks_ex(
        scope, hashes, fallback_title="★●經典の歐美無碼合集↘♀"
    )
    assert layout == "no_subtitle"
    assert len(blocks) == 3
    titles = [b.title for b in blocks]
    assert titles[0].startswith("OM1 ")
    assert titles[1].startswith("OM2 ")
    assert titles[2].startswith("OM10 ")
    assert all("經典" not in t for t in titles)
