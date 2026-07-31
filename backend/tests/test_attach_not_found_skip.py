# -*- coding: utf-8 -*-
"""附件 Not Found / 404 → 跳过「附件为空跳过」。"""

from __future__ import annotations

from parsers.attachments import (
    AttachmentFetchResult,
    is_attachment_not_found,
)
from workers.thread_outcome import judge_thread_html


def _html_with_txt_attach() -> str:
    return (
        """
    <html><head><title>【ED2K】示例合集 - 论坛</title></head>
    <body>
      <span id="thread_subject">【ED2K】示例合集【1V/1G】</span>
      <div id="postmessage_1">链接见附件</div>
      <div class="tattl"><ignore_js_op>
        <a href="forum.php?mod=attachment&aid=1">115ED2K下载链接.txt</a>
      </ignore_js_op></div>
      Powered by Discuz!
    </body></html>
    """
        + ("x" * 15000)
    )


def test_is_attachment_not_found_markers():
    assert is_attachment_not_found("<html>Not Found</html>") is True
    assert is_attachment_not_found("<title>404 Not Found</title>") is True
    assert is_attachment_not_found("抱歉，附件不存在或无法读入系统") is True
    assert is_attachment_not_found("附件不存在") is True
    assert is_attachment_not_found("<title>404</title><body></body>") is True
    assert is_attachment_not_found("只有特定用户可以下载本站附件") is False
    assert is_attachment_not_found("正常帖正文 aid=404123 不是 404 页") is False


def test_fetch_result_empty_attachment_flag():
    r = AttachmentFetchResult(empty_attachment=True)
    assert r.empty_attachment is True
    assert r.failed is False


def test_judge_attach_not_found_skips_empty():
    """tid=3437621 类：附件下载 Not Found → 附件为空跳过。"""
    out = judge_thread_html(
        _html_with_txt_attach(),
        board_fid="95:716",
        forum_id="sehuatang",
        list_title="【ED2K】示例合集【1V/1G】",
        preferred_link="ed2k",
        tid=3437621,
        attachments_already_tried=True,
        attachment_empty_attachment=True,
        attachment_failed=False,
        had_attachments=False,
    )
    assert out.verdict == "skipped"
    assert out.outcome == "附件为空跳过"


def test_judge_empty_attachment_beats_denied_stub_and_retry():
    out = judge_thread_html(
        _html_with_txt_attach(),
        board_fid="95:716",
        forum_id="sehuatang",
        list_title="【ED2K】示例合集【1V/1G】",
        preferred_link="ed2k",
        attachments_already_tried=True,
        attachment_empty_attachment=True,
        attachment_failed=True,
        had_attachments=False,
    )
    assert out.verdict == "skipped"
    assert out.outcome == "附件为空跳过"
