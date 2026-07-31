"""不完整抓取 → retry；完整无链 → 仍「未解析跳过」（勿扩大误报）。"""

from __future__ import annotations

from parsers.attachments import inject_attachment_text
from parsers.thread_gates import (
    looks_like_complete_thread_fetch,
    looks_like_incomplete_thread_fetch,
)
from workers.thread_outcome import judge_thread_html


def _pad(html: str, *, n: int = 900) -> str:
    return html + ("<!-- pad -->" * n)


def test_short_page_retries_not_skip_even_if_title_implies():
    """旧逻辑：title 像资源会先于「过短」直接未解析跳过。"""
    html = _pad(
        """
        <html><head><title>【ED2k】示例 - 站</title></head>
        <body>
          <span id="thread_subject">【ED2k】示例</span>
          <div id="postmessage_1">见下</div>
        </body></html>
        """,
        n=50,
    )
    assert len(html) < 8000
    assert looks_like_incomplete_thread_fetch(
        html, title="【ED2k】示例", link_kind="ed2k"
    )
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【ED2k】示例",
        preferred_link="ed2k",
    )
    assert out.verdict == "retry"
    assert "未完整" in out.outcome or "过短" in out.outcome or "未正常" in out.outcome
    assert "未解析" not in out.outcome


def test_see_attach_without_zone_retries():
    """正文写见附件，但 tattl 被截掉 → 不完整，勿未解析跳过。"""
    html = _pad(
        """
        <html><head><title>【115eD2k】合集资源 - 色花堂</title></head>
        <body>
          <span id="thread_subject">【115eD2k】合集资源</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">链接见附件，请下载附件查看</div>
            </div>
          </div>
          Powered by Discuz!
        </body></html>
        """
    )
    assert looks_like_incomplete_thread_fetch(
        html,
        title="【115eD2k】合集资源",
        list_title="【115eD2k】合集资源",
        link_kind="ed2k",
    )
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【115eD2k】合集资源",
        preferred_link="ed2k",
    )
    assert out.verdict == "retry"
    assert "未解析" not in out.outcome


def test_tiny_attach_inject_retries():
    """附件「已下」但注入极短（tip/空包）→ retry，勿未解析跳过。"""
    html = _pad(
        """
        <html><head><title>【ED2k】示例 - 站</title></head>
        <body>
          <span id="thread_subject">【ED2k】示例</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">见附件</div>
              <div class="tattl">
                <a href="forum.php?mod=attachment&amp;aid=1">links.txt</a>
              </div>
            </div>
          </div>
          Powered by Discuz!
        </body></html>
        """
    )
    html2 = inject_attachment_text(html, "暂无")
    out = judge_thread_html(
        html2,
        board_fid=103,
        list_title="【ED2k】示例",
        preferred_link="ed2k",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "retry"
    assert "未解析" not in out.outcome


def test_complete_page_no_link_still_skips():
    """完整长页、无附件指向、无目标链 → 仍未解析跳过（勿扩大重试）。"""
    html = _pad(
        """
        <html><head><title>版务通知请阅读 - 色花堂</title></head>
        <body>
          <span id="thread_subject">版务通知请阅读</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">
                本帖仅公告事务，不含任何下载地址。请勿跟帖催更。
                细则见置顶，感谢配合。abcdef ghijkl mnopqr stuvwx
              </div>
            </div>
          </div>
          Powered by Discuz!
        </body></html>
        """
    )
    assert len(html) >= 8000
    assert not looks_like_incomplete_thread_fetch(
        html, title="版务通知请阅读", link_kind="ed2k"
    )
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="版务通知请阅读",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "未解析" in out.outcome or "非资源" in out.outcome


def test_long_attach_no_target_still_skips():
    """已注入较长附件文本仍无 ed2k/磁力 → 真无链跳过，不因「已试附件」盲重试。"""
    html = _pad(
        """
        <html><head><title>【整理】目录说明 - 站</title></head>
        <body>
          <span id="thread_subject">【整理】目录说明</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">目录见附件</div>
              <div class="tattl">
                <a href="forum.php?mod=attachment&amp;aid=1">目录.txt</a>
              </div>
            </div>
          </div>
          Powered by Discuz!
        </body></html>
        """
    )
    catalog = "\n".join(f"条目{i} 仅说明无下载链" for i in range(40))
    html2 = inject_attachment_text(html, catalog)
    assert looks_like_complete_thread_fetch(
        html2,
        title="【整理】目录说明",
        list_title="【整理】目录说明",
        link_kind="ed2k",
        attachments_already_tried=True,
        had_attachments=True,
    )
    out = judge_thread_html(
        html2,
        board_fid=103,
        list_title="【整理】目录说明",
        preferred_link="ed2k",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "skipped"
    assert "未解析" in out.outcome


def test_long_page_without_footer_retries_not_skip():
    """长页但无论坛页脚：证据不足，勿永久未解析跳过。"""
    html = _pad(
        """
        <html><head><title>【ED2k】疑似半载 - 站</title></head>
        <body>
          <span id="thread_subject">【ED2k】疑似半载</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">
                正文已出但页尾未抓全时不应永久跳过。
                abcdefghijklmnopqrstuvwxyz0123456789
              </div>
            </div>
          </div>
        </body></html>
        """,
        n=2500,
    )
    assert len(html) >= 25000
    assert not looks_like_complete_thread_fetch(
        html, title="【ED2k】疑似半载", list_title="【ED2k】疑似半载", link_kind="ed2k"
    )
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【ED2k】疑似半载",
        preferred_link="ed2k",
    )
    assert out.verdict == "retry"
    assert "未解析" not in out.outcome


def test_attach_zone_without_try_not_complete_for_no_target():
    """有附件区却未试附件：不得认定完整到可「未解析跳过」。"""
    html = _pad(
        """
        <html><head><title>【ED2k】有附件 - 站</title></head>
        <body>
          <span id="thread_subject">【ED2k】有附件</span>
          <div id="postlist">
            <div id="post_1">
              <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
              <div id="postmessage_1">资源在附件</div>
              <div class="tattl">
                <a href="forum.php?mod=attachment&amp;aid=1">links.txt</a>
              </div>
            </div>
          </div>
          Powered by Discuz!
        </body></html>
        """
    )
    assert not looks_like_complete_thread_fetch(
        html,
        title="【ED2k】有附件",
        list_title="【ED2k】有附件",
        link_kind="ed2k",
        attachments_already_tried=False,
    )
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【ED2k】有附件",
        preferred_link="ed2k",
    )
    assert out.verdict == "need_attachments"
