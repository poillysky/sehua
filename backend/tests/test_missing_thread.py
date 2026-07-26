"""帖子不存在 / 没有找到帖子 → 明确跳过。"""

from __future__ import annotations

from parsers.thread_gates import is_empty_tip_page, is_missing_thread
from workers.thread_outcome import judge_thread_html


def test_is_missing_thread_没有找到帖子():
    html = """
    <html><head><title>提示信息 - 论坛</title></head>
    <body><div class="alert_error"><p>没有找到帖子</p></div>
    Powered by Discuz!</body></html>
    """
    assert is_missing_thread(html) is True
    out = judge_thread_html(html + ("x" * 2000), board_fid=103, preferred_link="both")
    assert out.verdict == "skipped"
    assert "不存在" in out.outcome


def test_missing_thread_not_confused_with_access_denied():
    html = """
    <html><head><title>提示信息</title></head>
    <body>本帖要求阅读权限高于 10 才能浏览
    Powered by Discuz!</body></html>
    """
    assert is_missing_thread(html) is False


def test_phpwind_empty_tip_is_retry_not_missing():
    """PHPWind 空提示信息页：先浏览器重试，勿永久标成帖子不存在。"""
    html = (
        "<html><head><title>提示信息</title></head>"
        "<body>返回继续操作 返回首页 Powered by PHPWind</body></html>"
        + ("x" * 3000)
    )
    assert is_missing_thread(html) is False
    assert is_empty_tip_page(html) is True
    out = judge_thread_html(
        html,
        board_fid="195",
        preferred_link="magnet",
        list_title="优质 BT · 魔王さまといっしょ",
    )
    assert out.verdict == "retry"
    assert out.need_browser_retry is True
    assert "提示页" in out.outcome

    out2 = judge_thread_html(
        html,
        board_fid="195",
        preferred_link="magnet",
        list_title="优质 BT · 魔王さまといっしょ",
        soft_browser_retried=True,
    )
    assert out2.verdict == "retry"
    assert out2.need_browser_retry is False
    assert "待重试" in out2.outcome


def test_short_tip_without_marker_not_missing():
    """旧逻辑：短提示信息无正文 → 误判不存在；现已取消。"""
    html = "<html><head><title>提示信息</title></head><body>ok</body></html>" + (
        "x" * 2000
    )
    assert is_missing_thread(html) is False
    assert is_empty_tip_page(html) is True
