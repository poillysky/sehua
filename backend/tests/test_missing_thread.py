"""帖子不存在 / 没有找到帖子 → 明确跳过。"""

from __future__ import annotations

from parsers.thread_gates import is_missing_thread
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
