# -*- coding: utf-8 -*-
"""结构卡片：先切【标签】再认角色。"""

from parsers.content import extract_metadata
from parsers.resource_names import clip_subresource_display_name
from parsers.structure_cards import (
    classify_structure_role,
    parse_structure_cards,
)


# 用户截图口径（无冒号亦可）
_SCREENSHOT_BLOB = """
【资源名称】超级美少女 无敌潮喷 屁股怼镜头开浆
【资源类型】视频
【是否有码】无码@有水印
【资源大小】2V/2G
【资源预览】
"""


def test_screenshot_five_fields_cards_and_roles():
    cards = parse_structure_cards(_SCREENSHOT_BLOB)
    by_role = {c.role: c for c in cards}
    assert by_role["name"].value.startswith("超级美少女")
    assert by_role["type"].value == "视频"
    assert by_role["coded"].value.startswith("无码")
    assert by_role["size"].value == "2V/2G"
    assert by_role["preview"].value == ""

    meta = extract_metadata(_SCREENSHOT_BLOB)
    assert meta.get("资源名称") == "超级美少女 无敌潮喷 屁股怼镜头开浆"
    assert meta.get("资源类型") == "视频"
    assert meta.get("资源大小") == "2V/2G"
    assert "资源类型" not in (meta.get("资源名称") or "")
    assert "是否有码" not in (meta.get("资源名称") or "")


def test_size_value_wrapped_in_decorative_brackets():
    """【资源大小】后无冒号、值再包【4.92GB/8V/8配额】（tid=3659150）。"""
    blob = """
【资源名称】：示例片名
【资源类型】：视频
【是否有码】：无码
【资源大小】  【4.92GB/8V/8配额】
【资源预览】：
"""
    meta = extract_metadata(blob)
    assert "4.92GB" in (meta.get("资源大小") or "")
    assert meta.get("资源大小") != ""

    from parsers.content import enrich_block_with_cards, build_structured_description
    from parsers.magnet import parse_capacity_bytes

    en = enrich_block_with_cards(blob, kind="resource", board_fid="95:716")
    assert en.size == parse_capacity_bytes("4.92GB")
    assert "4.92GB" in (en.size_label or "")
    assert "4.92GB" in (en.metadata.get("资源大小") or "")
    desc = build_structured_description(
        en.metadata, title=en.title, board_fid="95:716"
    )
    assert "【资源大小】" in desc and "4.92GB" in desc


def test_filename_not_polluted_by_type_size():
    raw = (
        "超级美少女 无敌潮喷 屁股怼镜头开浆"
        "【资源类型】视频【是否有码】无码@有水印【资源大小】2V/2G"
    )
    clipped = clip_subresource_display_name(raw)
    assert clipped == "超级美少女 无敌潮喷 屁股怼镜头开浆"
    assert "资源类型" not in clipped
    assert "2V/2G" not in clipped


def test_unknown_label_with_sep_still_splits():
    """未进历史白名单的标签，只要【】+分隔就能切开，不污染片名。"""
    blob = (
        "【资源名称】真片名ABC\n"
        "【发行片商】FOO工作室\n"
        "【资源大小】1.5G\n"
    )
    meta = extract_metadata(blob)
    assert meta.get("资源名称") == "真片名ABC"
    assert "发行片商" not in (meta.get("资源名称") or "")
    assert meta.get("资源大小") == "1.5G"
    # 未知标签仍可进 raw meta（描述白名单再过滤）
    assert meta.get("发行片商") == "FOO工作室"


def test_decorative_uncensored_tag_not_coded_role():
    assert classify_structure_role("高清無碼") == "other"
    assert classify_structure_role("是否有码") == "coded"
    assert classify_structure_role("资源名称") == "name"
    assert classify_structure_role("种子名称") == "torrent"
