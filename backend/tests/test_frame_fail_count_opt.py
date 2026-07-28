# -*- coding: utf-8 -*-
"""管理端不合格计数：无搜索时单次 FILTER 含 reviewed。"""

from __future__ import annotations


def test_count_frame_fail_filter_sql_includes_reviewed_bucket():
    """无 q/reason 路径应一次查出 reviewed，不依赖第二次 COUNT。"""
    import inspect

    from db import repository as repo

    src = inspect.getsource(repo.count_frame_fail_posts)
    assert "reviewed_n" in src
    assert "待审 ∪ 已审" in src or "reviewed_sql" in src
    # 旧「二次 COUNT 已审」不应再出现在无搜索主路径注释意图之后
    assert "AS reviewed_n" in src
