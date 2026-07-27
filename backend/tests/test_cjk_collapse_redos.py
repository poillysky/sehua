"""结构标签正则瘦身 + CJK 折叠不得 ReDoS。"""

from __future__ import annotations

import time

from parsers.content import LABEL_KEYS, _LABEL_ALT
from parsers.magnet import _collapse_cjk_inserted_spaces
from parsers.resource_names import collapse_cjk_inserted_spaces, structure_labels_alt


def test_collapse_cjk_spaces_no_redos_on_long_whitespace():
    blob = "资源" + (" \n" * 80) + "download attachment 下载附件"
    t0 = time.perf_counter()
    out = _collapse_cjk_inserted_spaces(blob)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.5, f"collapse too slow ({elapsed:.2f}s) — possible ReDoS"
    assert "资源" in out
    assert collapse_cjk_inserted_spaces(blob) == out


def test_collapse_cjk_keeps_anti_crawl_label():
    assert _collapse_cjk_inserted_spaces("【特 徵 碼】") == "【特徵碼】"
    assert _collapse_cjk_inserted_spaces("特·徵·碼") == "特徵碼"


def test_structure_label_alt_is_compact():
    """字面 alt 应远小于旧 flexible（曾达数万字符 / 三千分支）。"""
    assert len(_LABEL_ALT) < 8000, len(_LABEL_ALT)
    assert _LABEL_ALT.count("|") < 400, _LABEL_ALT.count("|")
    assert len(LABEL_KEYS) >= 50
    alt = structure_labels_alt(("影片名称", "影 片 名 称"))
    assert "影片名称" in alt
    assert "|" not in alt  # 归一后同一键
