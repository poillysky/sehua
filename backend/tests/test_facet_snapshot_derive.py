"""侧面栏统计：单维筛选从全局快照派生，避免扫库。"""

from db.repository import (
    _board_thread_count_from_facets,
    _derive_filtered_facets_from_global,
    _facet_all_from_global,
)


GLOBAL = {
    "sources": {"all": 1000, "web": 900, "upload": 100, "telegram": 0},
    "boards": [
        {"name": "亚洲有码原创", "count": 400},
        {"name": "亚洲有码原创 · 子类A", "count": 50},
        {"name": "国产原创 · 国产无码", "count": 200},
    ],
    "results": {
        "all": 1000,
        "magnet": 700,
        "ed2k": 200,
        "115share": 0,
        "stub": 100,
        "failed": 0,
        "multi": 30,
    },
    "forums": [
        {"id": "sehuatang", "name": "色花堂", "count": 980},
        {"id": "2048", "name": "2048", "count": 20},
    ],
}


def test_board_count_includes_children():
    assert _board_thread_count_from_facets(GLOBAL["boards"], "亚洲有码原创") == 450


def test_facet_all_single_dim():
    assert _facet_all_from_global(GLOBAL, board_name="亚洲有码原创") == 450
    assert _facet_all_from_global(GLOBAL, link_kind="magnet") == 700
    assert _facet_all_from_global(GLOBAL, forum_id="2048") == 20
    assert _facet_all_from_global(GLOBAL, source_type="upload") == 100
    # 多维不派生
    assert (
        _facet_all_from_global(GLOBAL, board_name="亚洲有码原创", link_kind="magnet")
        is None
    )


def test_derive_board_filter():
    out = _derive_filtered_facets_from_global(GLOBAL, board_name="亚洲有码原创")
    assert out is not None
    assert out["results"]["all"] == 450
    assert out["sources"]["all"] == 450
    assert sum(out["results"][k] for k in ("magnet", "ed2k", "115share", "stub", "failed")) == 450
    assert out["boards"][0]["name"] == "亚洲有码原创"
