"""启用多板队列：排序 / 切板 / 规范化。"""

from __future__ import annotations

from db.forum_configs import (
    _normalize_forum_config,
    next_enabled_board_fid,
    resolve_enabled_board_fids,
)


def test_resolve_enabled_respects_board_order():
    cfg = {
        "board_order": ["95", "2", "36", "103"],
        "enabled_board_fids": ["36", "95", "999"],
        "active_board_fid": "95",
    }
    assert resolve_enabled_board_fids(cfg) == ["95", "36"]


def test_resolve_enabled_falls_back_to_active():
    cfg = {
        "board_order": ["95", "2", "36"],
        "enabled_board_fids": [],
        "active_board_fid": "2",
    }
    assert resolve_enabled_board_fids(cfg) == ["2"]


def test_next_enabled_board_wraps():
    cfg = {
        "board_order": ["95", "2", "36"],
        "enabled_board_fids": ["95", "2", "36"],
    }
    assert next_enabled_board_fid(cfg, "95") == "2"
    assert next_enabled_board_fid(cfg, "2") == "36"
    assert next_enabled_board_fid(cfg, "36") == "95"
    assert next_enabled_board_fid(cfg, "999") == "95"


def test_normalize_migrates_legacy_active_to_enabled():
    cfg = _normalize_forum_config(
        {
            "active_board_fid": "36",
            "board_order": ["95", "2", "36"],
        }
    )
    assert cfg["enabled_board_fids"] == ["36"]
    assert cfg["active_board_fid"] == "36"

def test_normalize_drops_active_outside_enabled():
    cfg = _normalize_forum_config(
        {
            "board_order": ["95", "2", "36"],
            "enabled_board_fids": ["2", "36"],
            "active_board_fid": "95",
        }
    )
    assert cfg["enabled_board_fids"] == ["2", "36"]
    assert cfg["active_board_fid"] == "2"
