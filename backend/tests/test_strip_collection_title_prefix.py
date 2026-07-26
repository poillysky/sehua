"""Regression: 最强優片 first 【影片标题】 is '帖标题\\n真片名'."""
from __future__ import annotations

from parsers.content import _drop_thread_title_lines, _subresource_title_value


def test_drop_thread_title_multiline():
    title = "★★最强優片★★最強國產專輯A♂[05.31]"
    raw = f"{title}\n19岁宿舍学生妹06小烤肠下海福利"
    assert _drop_thread_title_lines(raw, title) == "19岁宿舍学生妹06小烤肠下海福利"


def test_drop_thread_title_prefix_collapsed():
    title = "★★最强優片★★最強國產專輯A♂[05.31]"
    raw = f"{title} 19岁宿舍学生妹06小烤肠下海福利"
    assert _drop_thread_title_lines(raw, title).startswith("19岁")


def test_subresource_title_value_strips_collection_header():
    title = "★★最强優片★★最強國產專輯A♂[05.31]"
    scope = (
        f"【影片标题】：{title}<br/>"
        "19岁宿舍学生妹06小烤肠下海福利，特写超粉嫩的小穴自慰诱惑<br/>"
        "【影片格式】：MP4<br/>"
        "【影片标题】：下一条"
    )
    # label ends after first 】
    import re

    m = re.search(r"【影片标题】", scope)
    assert m
    t_end = m.end()
    next_start = scope.index("【影片标题】", t_end)
    name = _subresource_title_value(
        scope, t_end, next_start, label_start=m.start(), thread_title=title
    )
    assert name.startswith("19岁")
    assert "最强優片" not in name
