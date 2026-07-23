"""合集帖：按真正子标题（影片名称/资源名称）切段挂预览图。"""

from __future__ import annotations

from parsers.content import extract_preview_images_by_infohash


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


def test_persist_uses_asset_preview_images(monkeypatch):
    from parsers.links import DualParseResult, ParsedAsset
    from db import persist as persist_mod

    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)

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
