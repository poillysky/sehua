"""处理记录按帖聚合：装配逻辑。"""

from __future__ import annotations

import pytest

from db.repository import (
    _assemble_thread_resource_row,
    _dedupe_preserve,
    _merge_preview_lists,
    _pick_thread_board_meta,
    _resource_list_where,
)


def test_dedupe_preserve_order():
    assert _dedupe_preserve(["a", "b", "a", "c", None, "b"]) == ["a", "b", "c"]


def test_merge_preview_lists_cap():
    got = _merge_preview_lists(
        [["u1", "u2"], ["u2", "u3"], ["u4"]],
        cap=3,
    )
    assert got == ["u1", "u2", "u3"]


def test_resource_list_where_rejects_multi_filter():
    """合集禁止走通用 WHERE（MULTI_ASSET_URL_SQL 相关子查询会卡死）。"""
    with pytest.raises(ValueError, match="multi"):
        _resource_list_where(link_kind="multi")
    where_sql2, params2 = _resource_list_where(link_kind="magnet")
    assert "magnet" in params2
    assert "GROUP BY" not in where_sql2


def test_resource_list_where_q_title_and_outcome():
    """资源列表关键字匹配标题/判定，不扫 search_string。"""
    sql, params = _resource_list_where(q="提示")
    assert "rs.title" in sql
    assert "import_outcome" in sql
    assert "search_string" not in sql
    assert params == ["%提示%", "%提示%"]


def test_resource_list_where_forum_id():
    """论坛筛选：空 forum_id 视为色花堂；all 不追加条件。"""
    sql_sht, params_sht = _resource_list_where(forum_id="sehuatang")
    assert "forum_id" in sql_sht
    assert "sehuatang" in params_sht

    sql_2048, params_2048 = _resource_list_where(forum_id="2048")
    assert "forum_id" in sql_2048
    assert params_2048 == ["2048"]

    sql_all, params_all = _resource_list_where(forum_id="all")
    assert "forum_id" not in sql_all
    assert params_all == []

    sql_empty, params_empty = _resource_list_where(forum_id="")
    assert "forum_id" not in sql_empty
    assert params_empty == []


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


def test_assemble_prefers_resolved_board_over_bench_junk():
    row = _assemble_thread_resource_row(
        group_id=1,
        updated_at=None,
        source_key="web:crawler",
        source_type="web",
        import_outcome="成功",
        assets_raw=[
            {
                "hash": "OLD",
                "filename": "旧",
                "size": 1,
                "ed2k_link": "ed2k://|file|old|1|AAAAAAAA|/",
                "title": "主标题",
                "description": "",
                "source_url": "https://www.sehuatang.net/thread-2663222-1-1.html",
                "board_fid": "103:480",
                "board_name": "bench",
                "ed2k_links": [],
                "extract_password": None,
                "forum_id": "sehuatang",
            },
            {
                "hash": "NEW",
                "filename": "新",
                "size": 2,
                "ed2k_link": "ed2k://|file|new|2|BBBBBBBB|/",
                "title": "主标题",
                "description": "",
                "source_url": "https://www.sehuatang.net/thread-2663222-1-1.html",
                "board_fid": "95:716",
                "board_name": "综合讨论区 · 情色分享",
                "ed2k_links": [],
                "extract_password": None,
                "forum_id": "sehuatang",
            },
        ],
    )
    assert row["board_fid"] == "95:716"
    assert row["board_name"] == "综合讨论区 · 情色分享"
    picked = _pick_thread_board_meta(
        [
            {"board_fid": "103:480", "board_name": "bench"},
            {"board_fid": "95:716", "board_name": "综合讨论区 · 情色分享"},
        ]
    )
    assert picked == ("95:716", "综合讨论区 · 情色分享")
