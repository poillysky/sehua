"""启用多板队列：子版 key / 旧 fid 展开 / 切板。"""

from __future__ import annotations

from db.forum_configs import (
    _normalize_forum_config,
    next_enabled_board_fid,
    resolve_enabled_board_fids,
)
from parsers.boards import expand_legacy_board_keys


def test_expand_legacy_fid_to_subunits():
    keys = expand_legacy_board_keys(["95"])
    assert keys == ["95:716"]
    # 其它 95 分类不进爬取单位
    assert "95:709" not in keys
    assert "95:662" not in keys


def test_resolve_enabled_respects_board_order():
    cfg = {
        "board_order": ["95:716", "95:709", "2:684", "37"],
        "enabled_board_fids": ["2:684", "95:716", "999"],
        "active_board_fid": "95:716",
    }
    assert resolve_enabled_board_fids(cfg) == ["95:716", "2:684"]


def test_resolve_enabled_expands_legacy_fid():
    cfg = {
        "board_order": expand_legacy_board_keys(["95", "2"]),
        "enabled_board_fids": ["95"],
        "active_board_fid": "95",
    }
    enabled = resolve_enabled_board_fids(cfg)
    assert enabled[0] == "95:716"
    assert all(k.startswith("95:") for k in enabled)


def test_resolve_enabled_falls_back_to_active():
    cfg = {
        "board_order": ["95:716", "2:684", "37"],
        "enabled_board_fids": [],
        "active_board_fid": "2:684",
    }
    assert resolve_enabled_board_fids(cfg) == ["2:684"]


def test_next_enabled_board_wraps():
    cfg = {
        "board_order": ["95:716", "2:684", "37"],
        "enabled_board_fids": ["95:716", "2:684", "37"],
    }
    assert next_enabled_board_fid(cfg, "95:716") == "2:684"
    assert next_enabled_board_fid(cfg, "2:684") == "37"
    assert next_enabled_board_fid(cfg, "37") == "95:716"
    assert next_enabled_board_fid(cfg, "999") == "95:716"


def test_normalize_migrates_legacy_active_to_enabled():
    cfg = _normalize_forum_config(
        {
            "active_board_fid": "36",
            "board_order": ["95", "2", "36"],
        }
    )
    assert all(k.startswith("36:") for k in cfg["enabled_board_fids"])
    assert cfg["active_board_fid"].startswith("36:")


def test_normalize_drops_active_outside_enabled():
    cfg = _normalize_forum_config(
        {
            "board_order": ["95:716", "2:684", "37"],
            "enabled_board_fids": ["2:684", "37"],
            "active_board_fid": "95:716",
        }
    )
    assert cfg["enabled_board_fids"] == ["2:684", "37"]
    assert cfg["active_board_fid"] == "2:684"


def test_list_url_for_subunit():
    from crawler.list_urls import list_url_for_board

    u = list_url_for_board("95:716", 1)
    assert "fid=95" in u
    assert "typeid=716" in u
    u2 = list_url_for_board("141:689", 2)
    assert "fid=141" in u2
    assert "typeid=689" in u2
    assert "page=2" in u2
    u3 = list_url_for_board("37", 1)
    assert "fid=37" in u3
    assert "typeid=" not in u3
