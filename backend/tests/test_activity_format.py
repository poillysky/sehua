"""activity_format unit checks."""

from workers.activity_format import format_thread_activity


def test_format_import_includes_detail_and_tid():
    msg = format_thread_activity(
        3436568,
        {
            "verdict": "import",
            "verdict_label": "正常入库",
            "outcome": "成功：已提取 1 条资源",
            "primary": "magnet",
            "link_kind": "magnet",
            "board_name": "高清中文字幕 · 有码高清",
            "title": "WANZ-883 demo",
            "magnets": 1,
            "ed2k": 0,
        },
    )
    assert "tid=3436568" in msg
    assert "正常入库" in msg
    assert "成功：已提取" in msg
    assert "magnet" in msg
    assert "磁力×1" in msg
    assert "WANZ-883" in msg


def test_format_skip_keeps_reason():
    msg = format_thread_activity(
        1,
        {
            "verdict": "skipped",
            "verdict_label": "跳过",
            "outcome": "版主屏蔽（跳过）",
            "link_kind": "none",
            "title": "x",
        },
        queue_note="跳过 · 已删占位",
    )
    assert "tid=1" in msg
    assert "已删占位" in msg
    assert "版主屏蔽" in msg


def test_random_prefix_dedupes_label():
    msg = format_thread_activity(
        9,
        {
            "verdict": "skipped",
            "verdict_label": "跳过",
            "outcome": "非资源帖",
            "title": "闲聊",
        },
        prefix="随机跳过",
    )
    assert msg.startswith("随机跳过 tid=9")
    assert " · 跳过 · " not in msg
    assert "非资源帖" in msg
