"""115sha 链接识别与跳过。"""

from __future__ import annotations

from parsers.attachments import inject_attachment_text
from parsers.thread_gates import has_115_sha_link
from workers.thread_outcome import judge_thread_html


SAMPLE_115 = (
    "115://【ChenYY】.rar|988137191|"
    "44A3BF496FAAB8126A657926431EAF7934DCA778|"
    "7F1DB1A9F83C83D4FF1CD36A4CA53282E1DF2D1F"
)

SAMPLE_115_MULTILINE = (
    "115://【ChenYY】.rar|\n"
    "988137191|\n"
    "44A3BF496FAAB8126A657926431EAF7934DCA778|\n"
    "7F1DB1A9F83C83D4FF1CD36A4CA53282E1DF2D1F"
)


def test_has_115_sha_link_matches_sample():
    assert has_115_sha_link(SAMPLE_115) is True
    assert has_115_sha_link(f'<div id="postmessage_1">{SAMPLE_115}</div>') is True
    assert has_115_sha_link(SAMPLE_115_MULTILINE) is True
    assert has_115_sha_link("magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01") is False
    assert has_115_sha_link("115://incomplete") is False


def test_judge_skips_115_sha_immediately():
    html = f"""
    <html><head><title>资源分享 - 论坛</title></head>
    <body>
    <div id="postmessage_1">{SAMPLE_115}</div>
    Powered by Discuz!
    </body></html>
    """
    # pad to avoid soft-shell length heuristics
    html = html + ("x" * 15000)
    out = judge_thread_html(html, board_fid=36, list_title="测试帖")
    assert out.verdict == "skipped"
    assert "115" in out.outcome


def test_judge_skips_115_sha_from_attachment_corpus():
    """正文无目标链，附件解析出 115sha → 立即 skipped。"""
    html = """
    <html><head><title>资源分享 - 论坛</title></head>
    <body>
    <div id="postmessage_1">本帖链接见附件</div>
    <div class="pattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=9">115链接.txt</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    # 模拟附件下载后注入语料再重判
    html2 = inject_attachment_text(html, SAMPLE_115_MULTILINE)
    out = judge_thread_html(
        html2,
        board_fid=36,
        list_title="测试帖",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "skipped"
    assert "附件" in out.outcome
