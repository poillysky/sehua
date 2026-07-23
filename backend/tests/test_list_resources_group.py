"""处理记录按帖聚合：装配逻辑。"""

from __future__ import annotations

from db.repository import _assemble_thread_resource_row, _dedupe_preserve, _merge_preview_lists


def test_dedupe_preserve_order():
    assert _dedupe_preserve(["a", "b", "a", "c", None, "b"]) == ["a", "b", "c"]


def test_merge_preview_lists_cap():
    got = _merge_preview_lists(
        [["u1", "u2"], ["u2", "u3"], ["u4"]],
        cap=3,
    )
    assert got == ["u1", "u2", "u3"]


def test_assemble_thread_merges_assets():
    row = _assemble_thread_resource_row(
        group_id=99,
        updated_at=None,
        source_key="web:crawler",
        source_type="web",
        import_outcome="成功：已提取 2 条资源",
        assets_raw=[
            {
                "hash": "AAA",
                "filename": "子1",
                "size": 1,
                "ed2k_link": "magnet:?xt=urn:btih:aaa",
                "preview_images": ["http://a/1.jpg"],
                "title": "主标题",
                "description": "desc",
                "source_url": "https://x/thread-1-1-1.html",
                "board_fid": "2",
                "board_name": "转帖",
                "ed2k_links": ["magnet:?xt=urn:btih:aaa"],
                "extract_password": None,
                "forum_id": "sehuatang",
            },
            {
                "hash": "BBB",
                "filename": "子2",
                "size": 2,
                "ed2k_link": "magnet:?xt=urn:btih:bbb",
                "preview_images": ["http://a/2.jpg"],
                "title": "主标题",
                "description": "desc",
                "source_url": "https://x/thread-1-1-1.html",
                "board_fid": "2",
                "board_name": "转帖",
                "ed2k_links": ["magnet:?xt=urn:btih:bbb"],
                "extract_password": None,
                "forum_id": "sehuatang",
            },
        ],
    )
    assert row["id"] == 99
    assert row["title"] == "主标题"
    assert row["hash"] == "AAA"
    assert row["hashes"] == ["AAA", "BBB"]
    assert row["asset_count"] == 2
    assert len(row["ed2k_links"]) == 2
    assert row["preview_images"] == ["http://a/1.jpg", "http://a/2.jpg"]
    assert row["link_kind"] == "magnet"
    assert row["forum_name"] == "色花堂"
