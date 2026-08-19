# -*- coding: utf-8 -*-
"""论坛壳标题剥离。"""

from parsers.content import strip_forum_shell_from_title, strip_forum_shell_from_text
from parsers.thread_gates import coalesce_thread_title


def test_strip_keeps_code_hyphen():
    raw = (
        "388GOJU-153 \u7fd4\u7530\u5343\u91cc - \u4e9a\u6d32\u6709\u7801\u539f\u521b"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert strip_forum_shell_from_title(raw) == "388GOJU-153 \u7fd4\u7530\u5343\u91cc"


def test_strip_board_and_site():
    raw = (
        "\u3010BT\u79cd\u5b50\u3011VENUS Pack - \u8f6c\u5e16\u4ea4\u6d41\u533a"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert strip_forum_shell_from_title(raw) == "\u3010BT\u79cd\u5b50\u3011VENUS Pack"


def test_strip_keeps_pure_shell():
    raw = "- \u8f6c\u5e16\u4ea4\u6d41\u533a - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    assert strip_forum_shell_from_title(raw) == raw


def test_strip_noop_clean_title():
    assert strip_forum_shell_from_title("\u6b63\u5e38\u6807\u9898\u65e0\u58f3") == "\u6b63\u5e38\u6807\u9898\u65e0\u58f3"


def test_strip_heji_title_not_board():
    raw = (
        "91\u56fd\u4ea7\u5408\u96c6 - \u6bcf\u65e5\u5408\u96c6"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert strip_forum_shell_from_title(raw) == "91\u56fd\u4ea7\u5408\u96c6"


def test_strip_title_ending_with_ban_not_board():
    raw = (
        "\u725b\u4ed4\u88e4\u5973\u53cb\u9ad8\u6e05\u7248 - \u56fd\u4ea7\u539f\u521b"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert strip_forum_shell_from_title(raw) == "\u725b\u4ed4\u88e4\u5973\u53cb\u9ad8\u6e05\u7248"


def test_strip_qiupian_board():
    raw = (
        "\u6c42\u8fd9\u90e8\u6b27\u7f8e\u7247\u7684\u9ad8\u6e05\u7248 - \u6c42\u7247\u95ee\u7b54\u60ac\u8d4f\u533a"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert strip_forum_shell_from_title(raw) == "\u6c42\u8fd9\u90e8\u6b27\u7f8e\u7247\u7684\u9ad8\u6e05\u7248"


def test_strip_text_description_line():
    raw = (
        "\u3010\u8d44\u6e90\u540d\u79f0\u3011\uff1aIPZ-862 - \u7efc\u5408\u8ba8\u8bba\u533a"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert "Powered" not in strip_forum_shell_from_text(raw)
    assert "IPZ-862" in strip_forum_shell_from_text(raw)


def test_coalesce_strips_shell():
    dirty = (
        "aoi-003 \u62c9\u4e01\u7cfb - \u4e9a\u6d32\u6709\u7801\u539f\u521b"
        " - 98\u5802[\u539f\u8272\u82b1\u5802] - Powered by Discuz!"
    )
    assert coalesce_thread_title(dirty) == "aoi-003 \u62c9\u4e01\u7cfb"
