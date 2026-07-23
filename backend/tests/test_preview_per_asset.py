"""合集帖：按真正子标题（影片名称/资源名称）切段挂预览图与磁力片名。"""

from __future__ import annotations

from parsers.content import (
    extract_preview_images_by_infohash,
    pair_magnet_to_subresource_title,
)


def test_preview_by_true_subtitle_film_name():
    """【影片名称】才是子标题；本标题到下一标题之间的图归本条。种子名称不算子标题。"""
    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      【种子名称】: a.torrent
      magnet:?xt=urn:btih:{h1}
      【影片名称】: 片子一
      <img file="https://cdn.example/shot_a1.jpg" src="https://cdn.example/t1.jpg" />
      <img file="https://cdn.example/shot_a2.jpg" src="https://cdn.example/t2.jpg" />
      【种子名称】: b.torrent
      magnet:?xt=urn:btih:{h2}
      【影片名称】: 片子二
      <img file="https://cdn.example/shot_b1.jpg" src="https://cdn.example/t3.jpg" />
    </div>
    """
    by_hash = extract_preview_images_by_infohash(html, [h1, h2], limit_per=5)
    assert by_hash[h1][0].endswith("shot_a1.jpg")
    assert by_hash[h1][1].endswith("shot_a2.jpg")
    assert by_hash[h2][0].endswith("shot_b1.jpg")
    assert not any(u.endswith("shot_b1.jpg") for u in by_hash[h1])


def test_seed_name_is_not_subtitle_boundary():
    """【种子名称】不能切开子资源块。"""
    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      magnet:?xt=urn:btih:{h1}
      【影片名称】: 片子一
      【影片截图】:
      <img file="https://cdn.example/a.jpg" src="https://cdn.example/ta.jpg" />
      【种子名称】: next.torrent
      magnet:?xt=urn:btih:{h2}
      【影片名称】: 片子二
      <img file="https://cdn.example/b.jpg" src="https://cdn.example/tb.jpg" />
    </div>
    """
    by_hash = extract_preview_images_by_infohash(html, [h1, h2], limit_per=3)
    assert by_hash[h1][0].endswith("a.jpg")
    assert by_hash[h2][0].endswith("b.jpg")


def test_preview_by_true_subtitle_resource_name():
    """【资源名称】同为真正子标题（综合/网友/转帖口径）。"""
    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      magnet:?xt=urn:btih:{h1}
      【资源名称】: 资源甲
      <img file="https://cdn.example/ra.jpg" src="https://cdn.example/tra.jpg" />
      magnet:?xt=urn:btih:{h2}
      【资源名称】: 资源乙
      <img file="https://cdn.example/rb.jpg" src="https://cdn.example/trb.jpg" />
    </div>
    """
    by_hash = extract_preview_images_by_infohash(html, [h1, h2], limit_per=5)
    assert by_hash[h1][0].endswith("ra.jpg")
    assert by_hash[h2][0].endswith("rb.jpg")


def test_preview_by_traditional_film_name():
    """繁体【影片名稱】同样切开子资源。"""
    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      magnet:?xt=urn:btih:{h1}
      【影片名稱】: 片子一
      <img file="https://cdn.example/ta.jpg" src="https://cdn.example/x1.jpg" />
      magnet:?xt=urn:btih:{h2}
      【影片名稱】: 片子二
      <img file="https://cdn.example/tb.jpg" src="https://cdn.example/x2.jpg" />
    </div>
    """
    by_hash = extract_preview_images_by_infohash(html, [h1, h2], limit_per=5)
    assert by_hash[h1][0].endswith("ta.jpg")
    assert by_hash[h2][0].endswith("tb.jpg")


def test_pair_magnet_title_same_as_preview_logic():
    """磁力在前、一个子标题：段内多磁力只保留第一条子资源。"""
    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      magnet:?xt=urn:btih:{h1}
      magnet:?xt=urn:btih:{h2}
      【影片名称】: [MP4/ 1.46G] 洗浴三闺蜜
      <img file="https://cdn.example/bath.jpg" src="https://cdn.example/t.jpg" />
      【影片名称】: 另一部
    </div>
    """
    titles = pair_magnet_to_subresource_title(html, [h1, h2])
    previews = extract_preview_images_by_infohash(html, [h1, h2], limit_per=3)
    assert h1 in titles
    assert "洗浴三闺蜜" in titles[h1]
    assert h2 not in titles  # 同属第一段，不另开子资源
    assert h1 in previews
    assert previews[h1][0].endswith("bath.jpg")
    assert h2 not in previews


def test_pair_title_then_magnet_layout():
    """BT 合集块：名称/大小/格式/说明/截图/磁力必须同一条。"""
    from parsers.content import extract_subresource_blocks
    from parsers.links import parse_thread_dual

    h1 = "27E43E540E38AD843DF864B593168984FB748ECD"
    h2 = "2D5EA65761943B5C3E2C7C8C3BE368CE815321BD"
    html = f"""
    <html><head><title>合集</title></head><body>
    <div id="postmessage_1">
      【影片名称】：[MP4/ 899M] 眼镜大叔单身宿舍约炮大长腿女同事各种姿势都要尝试一遍
      【影片大小】：899M
      【影片格式】：MP4
      【影片说明】：有/无码
      【影片截图】：
      <img file="https://cdn.example/a.jpg" src="https://cdn.example/ta.jpg" />
      【种子名称】: 06223 (1).torrent
      【磁力连接】: magnet:?xt=urn:btih:{h1}
      【影片名称】：[MP4/ 274M] 义乌抖音
      【影片大小】：274M
      【影片格式】：MP4
      【影片说明】：有/无码
      <img file="https://cdn.example/b.jpg" src="https://cdn.example/tb.jpg" />
      【种子名称】: b.torrent
      【磁力连接】: magnet:?xt=urn:btih:{h2}
    </div>
    </body></html>
    """
    blocks = {b.infohash: b for b in extract_subresource_blocks(html, [h1, h2])}
    b1 = blocks[h1]
    assert "眼镜大叔" in b1.title
    assert b1.size == 899 * 1024 * 1024
    assert b1.format.upper() == "MP4"
    assert "有" in b1.note and "码" in b1.note
    assert b1.torrent_name.startswith("06223")
    assert b1.preview_images[0].endswith("a.jpg")
    assert "【影片名称】" in b1.description
    assert "899M" in b1.description
    assert "【影片格式】：MP4" in b1.description
    assert blocks[h2].size == 274 * 1024 * 1024
    assert blocks[h2].preview_images[0].endswith("b.jpg")

    parsed = parse_thread_dual(html, tid=3580931, preferred_link="magnet")
    by_hash = {a.hash.upper(): a for a in parsed.assets}
    assert "眼镜大叔" in (by_hash[h1].filename or "")
    assert by_hash[h1].size == 899 * 1024 * 1024
    assert by_hash[h1].preview_images[0].endswith("a.jpg")
    assert "899M" in (by_hash[h1].description or "")
    assert "义乌抖音" in (by_hash[h2].filename or "")
    assert by_hash[h2].size == 274 * 1024 * 1024


def test_resource_name_block_still_works():
    """综合/网友口径：【资源名称】仍作子标题切段，描述键保持资源*。"""
    from parsers.content import extract_subresource_blocks

    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      【资源名称】：综合真名甲
      【资源大小】：1.2G
      【资源类型】：影片
      【资源说明】：无码
      <img file="https://cdn.example/ra.jpg" src="https://cdn.example/tra.jpg" />
      【磁力连接】: magnet:?xt=urn:btih:{h1}
      【资源名称】：综合真名乙
      【资源大小】：500M
      magnet:?xt=urn:btih:{h2}
    </div>
    """
    blocks = {b.infohash: b for b in extract_subresource_blocks(html, [h1, h2])}
    assert blocks[h1].title == "综合真名甲"
    assert blocks[h1].size == int(1.2 * 1024**3)
    assert blocks[h1].format == "影片"
    assert "【资源名称】：综合真名甲" in blocks[h1].description
    assert "【资源大小】：1.2G" in blocks[h1].description
    assert "【资源类型】：影片" in blocks[h1].description
    assert blocks[h1].preview_images[0].endswith("ra.jpg")
    assert blocks[h2].title == "综合真名乙"
    assert blocks[h2].size == 500 * 1024 * 1024


def test_traditional_resource_block_variants():
    """繁体/异写：資源名稱、資源大小、資源類型、種子名稱、磁力連結。"""
    from parsers.content import extract_subresource_blocks
    from parsers.resource_names import SUBRESOURCE_TITLE_MATCH_FORMS

    assert "視頻名稱" in SUBRESOURCE_TITLE_MATCH_FORMS
    assert "作品名稱" in SUBRESOURCE_TITLE_MATCH_FORMS
    assert "片名" in SUBRESOURCE_TITLE_MATCH_FORMS

    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <div id="postmessage_1">
      【資源名稱】：繁體資源甲
      【資源大小】：899M
      【資源類型】：影片
      【資源說明】：無碼
      【種子名稱】: a.torrent
      【磁力連結】: magnet:?xt=urn:btih:{h1}
      【作品名稱】：繁體作品乙
      【檔案大小】：274M
      【磁力連接】: magnet:?xt=urn:btih:{h2}
    </div>
    """
    blocks = {b.infohash: b for b in extract_subresource_blocks(html, [h1, h2])}
    assert blocks[h1].title == "繁體資源甲"
    assert blocks[h1].size == 899 * 1024 * 1024
    assert blocks[h1].format == "影片"
    assert "【资源名称】：繁體資源甲" in blocks[h1].description
    assert "899M" in blocks[h1].description
    assert blocks[h1].torrent_name.startswith("a.torrent")
    assert blocks[h2].title == "繁體作品乙"
    assert blocks[h2].size == 274 * 1024 * 1024


def test_parse_thread_dual_overrides_filename_from_span():
    """合集解析：asset.filename 用切段片名，而不是语料就近误绑。"""
    from parsers.links import parse_thread_dual

    h1 = "A14DF0858322E3D03BF0B2A1A2C781108602A3E1"
    h2 = "8585E3735BDD7C467B50047BC08BB472400C8CF4"
    html = f"""
    <html><head><title>合集帖</title></head><body>
    <div id="postmessage_1">
      【影片名称】: 片子一正确
      magnet:?xt=urn:btih:{h1}
      <img file="https://cdn.example/a.jpg" src="https://cdn.example/ta.jpg" />
      【影片名称】: 片子二正确
      magnet:?xt=urn:btih:{h2}
      <img file="https://cdn.example/b.jpg" src="https://cdn.example/tb.jpg" />
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=1, preferred_link="magnet")
    assert len(parsed.assets) == 2
    by_hash = {a.hash.upper(): a for a in parsed.assets}
    assert by_hash[h1].filename == "片子一正确"
    assert by_hash[h2].filename == "片子二正确"
    assert by_hash[h1].preview_images[0].endswith("a.jpg")
    assert by_hash[h2].preview_images[0].endswith("b.jpg")


def test_two_magnets_without_subtitles_keep_primary_only():
    """无【影片名称】：子标题=帖标题，段内多个磁力只留一条子资源。"""
    from parsers.links import parse_thread_dual

    h1 = "20D70DBFC950B719335BCED87AEE73DFB6848301"
    h2 = "5E94DB4CD39507AFB10CBE224A57F2D9DC72865D"
    html = f"""
    <html><head><title>单资源双链</title></head><body>
    <span id="thread_subject">单资源双链</span>
    <div id="postmessage_1">
      下载链接：
      magnet:?xt=urn:btih:{h1}
      备用：
      magnet:?xt=urn:btih:{h2}
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=929130, preferred_link="magnet")
    assert len(parsed.assets) == 1
    assert parsed.assets[0].hash.upper() == h1
    assert parsed.assets[0].is_primary
    assert "单资源双链" in (parsed.assets[0].filename or "")


def test_one_subtitle_owns_all_magnets_in_segment():
    """一个子标题：段内多个磁力仍只产出一条子资源。"""
    from parsers.links import parse_thread_dual

    h1 = "20D70DBFC950B719335BCED87AEE73DFB6848301"
    h2 = "5E94DB4CD39507AFB10CBE224A57F2D9DC72865D"
    html = f"""
    <html><body>
    <div id="postmessage_1">
      【影片名称】：唯一片名
      magnet:?xt=urn:btih:{h1}
      magnet:?xt=urn:btih:{h2}
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=1, preferred_link="magnet")
    assert len(parsed.assets) == 1
    assert parsed.assets[0].hash.upper() == h1
    assert parsed.assets[0].filename == "唯一片名"


def test_persist_uses_asset_preview_images(monkeypatch):
    from parsers.links import DualParseResult, ParsedAsset
    from db import persist as persist_mod

    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)
    monkeypatch.setattr(persist_mod, "delete_stub_by_source_url", lambda *a, **k: False)

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append({"hash": link.hash, "preview": kwargs.get("preview_images")})
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)

    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename="子A",
            size=1,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
            preview_images=["https://cdn.example/a.jpg"],
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename="子B",
            size=1,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
            preview_images=["https://cdn.example/b.jpg"],
        ),
    ]
    parsed = DualParseResult(
        tid=1,
        title="合集",
        description="",
        metadata={},
        preview_images=["https://cdn.example/shared.jpg"],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
    )
    persist_mod.persist_dual_parse(
        object(), parsed, source_url="https://x/thread-1-1-1.html"
    )
    assert calls[0]["preview"] == ["https://cdn.example/a.jpg"]
    assert calls[1]["preview"] == ["https://cdn.example/b.jpg"]
