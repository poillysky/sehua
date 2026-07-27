"""结构字段：自动识别括号样式，遇下一标签开括号即切（不问标签名是否白名单）。

样例口径：
  【影片格式】：MP4 【字幕语言】：无
  【影片大小】：2.47GB
"""

from parsers.content import (
    _clip_field_value,
    build_structured_description,
    extract_metadata,
)
from parsers.resource_names import (
    clip_subresource_display_name,
    detect_structure_bracket_pair,
)


_ABF261_BLOB = (
    "【影片名称】：ABF-261 耳元でそっとささやく家庭崩壊確定な不倫のお誘い。 七嶋舞\n"
    "【影片格式】：MP4 【字幕语言】：无\n"
    "【影片大小】：2.47GB\n"
)


def test_detect_bracket_pair_prefers_fullwidth():
    assert detect_structure_bracket_pair(_ABF261_BLOB) == ("【", "】")


def test_detect_bracket_pair_halfwidth():
    text = "[Film Name]: Foo\n[Film Size]: 1.2GB\n"
    assert detect_structure_bracket_pair(text) == ("[", "]")


def test_clip_format_stops_at_unknown_label_same_line():
    """未入库白名单的标签名，只要成对括号+分隔，格式值仍截断。"""
    assert (
        _clip_field_value("MP4 【字幕语言】：无", label="影片格式") == "MP4"
    )
    assert (
        _clip_field_value("MP4 【从未见过的字段】：xxx", label="影片格式") == "MP4"
    )
    assert _clip_field_value("2.47GB", label="影片大小") == "2.47GB"
    assert (
        _clip_field_value("2.47GB 【发行片商】：FOO", label="影片大小") == "2.47GB"
    )


def test_clip_title_stops_at_unknown_labeled_field_keeps_decorative():
    raw = "FC2-PPV-1 受付嬢【高清無碼】 【从未见过的字段】：MP4"
    assert _clip_field_value(raw, label="影片名称") == "FC2-PPV-1 受付嬢【高清無碼】"
    assert "高清無碼" in clip_subresource_display_name(raw)


def test_extract_metadata_abf261_glued_format_subtitle():
    meta = extract_metadata(_ABF261_BLOB)
    assert meta.get("影片名称", "").startswith("ABF-261")
    assert "影片格式" not in meta.get("影片名称", "")
    assert "影片大小" not in meta.get("影片名称", "")
    assert meta.get("影片格式") == "MP4"
    assert meta.get("影片大小") == "2.47GB"
    # 未进描述白名单的标签可不入库，但不得污染上一字段


def test_structured_description_one_label_per_line():
    meta = extract_metadata(_ABF261_BLOB)
    desc = build_structured_description(
        meta,
        title=meta.get("影片名称") or "",
        board_fid="36",
    )
    lines = [ln for ln in desc.splitlines() if ln.strip()]
    assert lines, desc
    for ln in lines:
        assert ln.count("【") == 1, ln
        assert ln.count("】") == 1, ln
    assert not any("字幕" in ln for ln in lines)
    assert any(ln.startswith("【影片格式】") and ln.endswith("MP4") for ln in lines)
    assert any("2.47GB" in ln and "大小】" in ln for ln in lines)


def test_structured_description_no_name_size_glued():
    meta = {
        "影片名称": "ABF-261 七嶋舞",
        "影片格式": "MP4",
        "影片大小": "2.47GB",
    }
    desc = build_structured_description(meta, title="ABF-261 七嶋舞", board_fid="36")
    for ln in desc.splitlines():
        if not ln.strip():
            continue
        assert ln.count("【") == 1, ln
    assert "【影片名称】" in desc
    size_lines = [ln for ln in desc.splitlines() if "大小】" in ln]
    assert size_lines
    for ln in size_lines:
        assert "名称" not in ln.split("】", 1)[-1]
        assert ln.count("【") == 1
