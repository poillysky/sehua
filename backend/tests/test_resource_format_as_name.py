# -*- coding: utf-8 -*-
"""2048 国产合集：无【影片名称】时用【资源格式】作子名（tid=27189104）。"""
from __future__ import annotations

from parsers.content import _name_before_size_label, extract_subresource_blocks_ex
from parsers.magnet import parse_magnet_text


def test_name_before_size_strips_download_url_noise():
    scope = (
        '396463D6" onclick=copy>复制 【下载网址】: '
        "【资源格式】：微胖韵味良家人妻,白色衬衫仙气飘飘"
        "【影片大小】：1.1GB"
    )
    idx = scope.index("【影片大小】")
    name = _name_before_size_label(scope, idx, thread_title="★◇合集")
    assert name.startswith("微胖韵味")
    assert "资源格式" not in name
    assert "下载网址" not in name


def test_name_before_size_keeps_short_cjk():
    """容量前短中文名勿因 len<4 丢弃。"""
    scope = "油鬼子【影片大小】：500MB"
    idx = scope.index("【影片大小】")
    name = _name_before_size_label(scope, idx, thread_title="合集标题")
    assert name == "油鬼子"


def test_resource_format_blocks_have_distinct_titles():
    """size_then_magnet 切段时，各块【资源格式】应成为独立子名。"""
    hashes = [f"{i:02X}" * 20 for i in range(3)]
    chunks = []
    for i, h in enumerate(hashes):
        chunks.append(
            f"【资源格式】：独立片名{i}足够长不会被裁\n"
            f"【影片大小】：{1 + i}.0GB\n"
            f"magnet:?xt=urn:btih:{h}\n"
        )
    scope = "\n".join(chunks)
    blocks, layout = extract_subresource_blocks_ex(
        scope,
        hashes,
        fallback_title="★◇合集标题",
    )
    assert layout == "size_then_magnet"
    assert len(blocks) == 3
    titles = [b.title for b in blocks]
    assert len(set(titles)) == 3
    assert all(f"独立片名{i}" in titles[i] for i in range(3))
    assert all("★◇" not in (t or "") for t in titles)
