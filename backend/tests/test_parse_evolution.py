"""Unit tests for parse-evolution classify + judge."""
from __future__ import annotations

from types import SimpleNamespace

from parsers.evolution.classify import classify_title
from parsers.evolution.judge import judge_parsed


def test_classify_tj1221_and_guochan():
    assert classify_title("▲tj1221▲最新马克赛破坏强片合集").startswith("tj1221")
    assert classify_title("★★灣搭★中字合集") == "湾搭_中字"
    assert "国产" in classify_title("★◇精彩の最新國產合集")


def test_judge_clean_multi_ok():
    assets = [
        SimpleNamespace(filename=f"CODE-{i}", preview_images=[f"http://img/{i}.jpg"])
        for i in range(5)
    ]
    out = judge_parsed(title="干净合集标题", assets=assets, title_spans=5)
    assert out["ok"] is True
    assert out["issues"] == []


def test_judge_catches_shared_preview_and_title_suffix():
    img = ["http://same.jpg"]
    assets = [
        SimpleNamespace(filename="A", preview_images=img),
        SimpleNamespace(filename="B", preview_images=img),
        SimpleNamespace(filename="C", preview_images=img),
    ]
    out = judge_parsed(title="片名 | 最新合集", assets=assets)
    assert out["ok"] is False
    assert "title_suffix" in out["issues"] or "title_board_suffix" in out["issues"]
    assert "shared_preview" in out["issues"]


def test_judge_empty_assets_not_ok():
    out = judge_parsed(title="某合集", assets=[], title_spans=1)
    assert out["ok"] is False
    assert "empty_assets" in out["issues"]
