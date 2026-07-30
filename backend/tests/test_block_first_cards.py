# -*- coding: utf-8 -*-
"""先切资源块，再块内卡片：隔离与单块回落。"""

from parsers.content import enrich_block_with_cards, extract_subresource_blocks
from parsers.links import parse_thread_dual


def test_two_name_blocks_cards_isolated():
    """两片名+两链：大小/图/描述互不串块。"""
    h1 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    h2 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    html = f"""
    <html><head><title>合集帖</title></head><body>
    <div id="postmessage_1">
      【影片名称】：甲片专用名
      【影片大小】：1.1G
      【影片格式】：MP4
      【影片说明】：无码
      <img file="https://cdn.example/a-only.jpg" src="https://cdn.example/ta.jpg" />
      magnet:?xt=urn:btih:{h1}
      【影片名称】：乙片专用名
      【影片大小】：2.2G
      【影片格式】：MKV
      【影片说明】：有码
      <img file="https://cdn.example/b-only.jpg" src="https://cdn.example/tb.jpg" />
      magnet:?xt=urn:btih:{h2}
    </div>
    </body></html>
    """
    blocks = {b.infohash: b for b in extract_subresource_blocks(html, [h1, h2])}
    assert set(blocks) == {h1, h2}
    b1, b2 = blocks[h1], blocks[h2]
    assert "甲片专用名" in b1.title
    assert "乙片专用名" in b2.title
    assert "乙片" not in b1.title and "甲片" not in b2.title
    assert b1.size == int(1.1 * 1024**3)
    assert b2.size == int(2.2 * 1024**3)
    assert b1.preview_images[0].endswith("a-only.jpg")
    assert b2.preview_images[0].endswith("b-only.jpg")
    assert "1.1G" in b1.description and "2.2G" not in b1.description
    assert "2.2G" in b2.description and "1.1G" not in b2.description
    assert b1.metadata.get("影片大小") == "1.1G" or "1.1G" in (
        b1.metadata.get("资源大小") or ""
    )
    assert "2.2G" not in " ".join(b1.metadata.values())

    parsed = parse_thread_dual(html, tid=900001, preferred_link="magnet")
    # 多资源：帖级 meta 清空，明细在 asset
    assert parsed.metadata == {}
    by_hash = {a.hash.upper(): a for a in parsed.assets}
    assert "甲片专用名" in (by_hash[h1].filename or "")
    assert "乙片专用名" in (by_hash[h2].filename or "")
    assert by_hash[h1].preview_images[0].endswith("a-only.jpg")
    assert by_hash[h2].preview_images[0].endswith("b-only.jpg")


def test_no_name_label_single_magnet_falls_back_to_title():
    """无名称标签 + 单链 → 恰好一块，名回落帖标题。"""
    h1 = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
    html = f"""
    <html><head><title>回落片名XYZ - 论坛</title></head><body>
    <div id="postmessage_1">
      随便介绍一下
      【影片大小】：500M
      magnet:?xt=urn:btih:{h1}
    </div>
    </body></html>
    """
    blocks = extract_subresource_blocks(
        html, [h1], fallback_title="回落片名XYZ"
    )
    assert len(blocks) == 1
    assert blocks[0].infohash == h1
    assert "回落片名XYZ" in blocks[0].title
    assert blocks[0].size == 500 * 1024 * 1024

    parsed = parse_thread_dual(html, tid=900002, preferred_link="magnet")
    assert len([a for a in parsed.assets if a.link_kind == "magnet"]) == 1
    primary = next(a for a in parsed.assets if a.is_primary)
    assert "回落片名XYZ" in (primary.filename or parsed.title or "")
    assert primary.size == 500 * 1024 * 1024
    # 单资源：帖级可用块 meta
    assert parsed.metadata.get("影片大小") == "500M" or parsed.metadata.get(
        "资源大小"
    ) == "500M" or "500M" in (primary.description or "")


def test_single_block_five_fields_like_3657919():
    """单块五字段：资源名称等进 asset，不污染为整帖串味。"""
    h1 = "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
    blob = """
【资源名称】超级美少女 无敌潮喷 屁股怼镜头开浆
【资源类型】视频
【是否有码】无码@有水印
【资源大小】2V/2G
【资源预览】
"""
    enriched = enrich_block_with_cards(blob, kind="resource")
    assert enriched.title.startswith("超级美少女")
    assert "资源类型" not in enriched.title
    assert enriched.size > 0
    assert "2V/2G" in enriched.description or "2G" in enriched.description
    assert enriched.metadata.get("资源名称", "").startswith("超级美少女")
    assert enriched.metadata.get("资源类型") == "视频"

    html = f"""
    <html><head><title>五字段帖</title></head><body>
    <div id="postmessage_1">
      {blob}
      magnet:?xt=urn:btih:{h1}
    </div>
    </body></html>
    """
    blocks = extract_subresource_blocks(html, [h1], fallback_title="五字段帖")
    assert len({(b.title or "").strip() for b in blocks}) == 1
    b0 = blocks[0]
    assert "超级美少女" in b0.title
    assert "视频" not in b0.title
    parsed = parse_thread_dual(html, tid=900003, preferred_link="magnet")
    primary = next(a for a in parsed.assets if a.is_primary)
    assert "超级美少女" in (primary.filename or "")
    assert "资源类型" not in (primary.filename or "")
