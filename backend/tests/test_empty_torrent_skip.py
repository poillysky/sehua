"""空壳种子（0 字节）→ 跳过「种子大小为0」，勿「附件下载失败」重试。"""

from __future__ import annotations

from parsers.attachments import AttachmentFetchResult
from workers.thread_outcome import judge_thread_html


def _html_torrent_only() -> str:
    return """
    <html><head><title>示例合集</title></head>
    <body>
      <h1 id="thread_subject">2048独家合集 示例【1V/1GB】</h1>
      <div class="tpc_content">正文无磁力只有附件</div>
      <div class="tattl">
        <a href="job.php?action=download&aid=1">demo.torrent</a>
        <span>大小：0 K</span>
      </div>
    </body></html>
    """


def test_attachment_fetch_result_empty_torrent_flag():
    r = AttachmentFetchResult(empty_torrent=True)
    assert r.empty_torrent is True
    assert r.failed is False
    assert AttachmentFetchResult().empty_torrent is False


def test_judge_empty_torrent_skips_not_retry():
    html = _html_torrent_only()
    out = judge_thread_html(
        html,
        board_fid="103",
        list_title="2048独家合集 示例【1V/1GB】",
        base_url="https://bbs.sbnlfe.cn/read.php?tid=1",
        forum_id="2048",
        preferred_link="magnet",
        attachments_already_tried=True,
        attachment_empty_torrent=True,
        attachment_failed=False,
        had_attachments=False,
    )
    assert out.verdict == "skipped"
    assert out.outcome == "种子大小为0"


def test_judge_empty_torrent_beats_failed_retry():
    """同时带 failed 时仍优先空壳跳过（勿重试）。"""
    html = _html_torrent_only()
    out = judge_thread_html(
        html,
        board_fid="103",
        list_title="2048独家合集 示例【1V/1GB】",
        base_url="https://bbs.sbnlfe.cn/read.php?tid=1",
        forum_id="2048",
        preferred_link="magnet",
        attachments_already_tried=True,
        attachment_empty_torrent=True,
        attachment_failed=True,
        had_attachments=False,
    )
    assert out.verdict == "skipped"
    assert out.outcome == "种子大小为0"


def test_judge_attach_failed_still_retries_when_not_empty():
    html = _html_torrent_only()
    out = judge_thread_html(
        html,
        board_fid="103",
        list_title="2048独家合集 示例【1V/1GB】",
        base_url="https://bbs.sbnlfe.cn/read.php?tid=1",
        forum_id="2048",
        preferred_link="magnet",
        attachments_already_tried=True,
        attachment_empty_torrent=False,
        attachment_failed=True,
        had_attachments=False,
    )
    assert out.verdict == "retry"
    assert "附件下载失败" in (out.outcome or "")
