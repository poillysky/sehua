"""合集帖磁力旁真正子标题（影片名称/资源名称）识别。"""

from __future__ import annotations

from parsers.magnet import parse_magnet_text
from parsers.resource_names import SUBRESOURCE_TITLE_LABELS, SUBRESOURCE_TITLE_MATCH_FORMS


def test_subresource_title_labels_frozen():
    """规范键仍是影片名称/资源名称；匹配表含简繁异写。"""
    assert SUBRESOURCE_TITLE_LABELS == ("影片名称", "资源名称")
    for lab in (
        "影片名稱",
        "資源名稱",
        "視頻名稱",
        "作品名稱",
        "片名",
        "资源名",
        "影片标题",
    ):
        assert lab in SUBRESOURCE_TITLE_MATCH_FORMS


def test_parse_magnet_uses_film_name_label():
    text = """
    【种子名称】: 07231 (1).torrent
    【磁力连接】: magnet:?xt=urn:btih:A14DF0858322E3D03BF0B2A1A2C781108602A3E1
    【影片名称】:[MP4/ 1.02G] 巨乳东北大姐 宝贝用力操我啊
    【影片大小】:1.02G
    【种子名称】: 07231 (2).torrent
    【磁力连接】: magnet:?xt=urn:btih:8585E3735BDD7C467B50047BC08BB472400C8CF4
    【影片名称】:[MP4/ 413M] 乱伦大神意淫自己妹妹
    【影片大小】:413M
    """
    links = parse_magnet_text(text)
    assert len(links) == 2
    assert "巨乳东北大姐" in links[0].filename
    assert links[0].size == int(1.02 * 1024**3)
    assert "乱伦大神" in links[1].filename
    assert links[1].size == 413 * 1024**2


def test_parse_magnet_uses_traditional_film_name():
    text = """
    magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    【影片名稱】: 繁體片子甲
    magnet:?xt=urn:btih:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
    【影片名稱】: 繁體片子乙
    """
    links = parse_magnet_text(text)
    assert len(links) == 2
    assert links[0].filename == "繁體片子甲"
    assert links[1].filename == "繁體片子乙"


def test_parse_magnet_uses_resource_name_label():
    text = """
    magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
    【资源名称】: 综合区合集甲
    magnet:?xt=urn:btih:BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB
    【资源名称】: 综合区合集乙
    """
    links = parse_magnet_text(text)
    assert len(links) == 2
    assert links[0].filename == "综合区合集甲"
    assert links[1].filename == "综合区合集乙"


def test_parse_magnet_prefers_label_over_dn():
    text = """
    【种子名称】: ignore.torrent
    magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&dn=real-name.mp4
    【影片名称】: should-win
    """
    links = parse_magnet_text(text)
    assert len(links) == 1
    assert links[0].filename == "should-win"
