"""易混淆误判：标题写 115eD2k，正文夹带蓝奏推广链时，应先试附件。"""

from __future__ import annotations

from workers.thread_outcome import judge_thread_html


def _pad(html: str) -> str:
    return html + ("<!-- pad -->" * 900)


def test_title_115ed2k_with_lanzou_promo_tries_attachment():
    html = _pad(
        """
        <html><head><title>【自转】【百度网盘+115eD2k】示例 - 论坛</title></head>
        <body>
        <span id="thread_subject">【自转】【百度网盘+115eD2k】示例</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">
              安卓手机可以下载这个： https://wwsx.lanzouw.com/iZq9b35t2p2h 密码:fwnu
              真正链见附件
            </div>
            <div class="tattl"><ignore_js_op>
              <a href="forum.php?mod=attachment&aid=1">115ED2K下载链接.txt</a>
            </ignore_js_op></div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    out = judge_thread_html(
        html,
        board_fid="95",
        list_title="【自转】【百度网盘+115eD2k】示例",
        preferred_link="ed2k",
        forum_id="sehuatang",
    )
    assert out.verdict == "need_attachments", out.outcome
    assert "蓝奏" not in (out.outcome or "")


def test_attach_115sha_only_not_labeled_unparsed():
    from parsers.attachments import inject_attachment_text

    html = _pad(
        """
        <html><head><title>【115sha1】示例合集 - 论坛</title></head>
        <body>
        <span id="thread_subject">【115sha1】示例合集</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">见附件</div>
            <div class="tattl"><ignore_js_op>
              <a href="forum.php?mod=attachment&aid=1">demo_sha1.rar</a>
            </ignore_js_op></div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    attach = (
        "115://demo.mkv|12345|7914413E01CF908E805BB40B0339C924BF0E4292|"
        "7914413E01CF908E805BB40B0339C924BF0E4292\n"
    )
    html2 = inject_attachment_text(html, attach)
    out = judge_thread_html(
        html2,
        board_fid="104",
        list_title="【115sha1】示例合集",
        preferred_link="magnet",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "skipped"
    assert "115sha" in out.outcome.lower() or "115" in out.outcome
    assert "未解析到" not in out.outcome


def test_title_115ed2k_with_quark_promo_tries_attachment():
    html = _pad(
        """
        <html><head><title>【整理】【115eD2k/夸克】示例三部合 - 论坛</title></head>
        <body>
        <span id="thread_subject">【整理】【115eD2k/夸克】示例三部合</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">
              夸克备用： https://pan.quark.cn/s/abc123XYZ
              真链见附件
            </div>
            <div class="tattl"><ignore_js_op>
              <a href="forum.php?mod=attachment&aid=1">防失效备用版.txt</a>
            </ignore_js_op></div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    out = judge_thread_html(
        html,
        board_fid="95",
        list_title="【整理】【115eD2k/夸克】示例三部合",
        preferred_link="ed2k",
        forum_id="sehuatang",
    )
    assert out.verdict == "need_attachments", out.outcome
    assert "夸克" not in (out.outcome or "")


def test_cloud_attach_denied_stubs_not_cloud_skip():
    html = _pad(
        """
        <html><head><title>【自转】【百度网盘+115eD2k】示例 - 论坛</title></head>
        <body>
        <span id="thread_subject">【自转】【百度网盘+115eD2k】示例</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">
              https://wwsx.lanzouw.com/iZq9b35t2p2h
            </div>
            <div class="tattl"><ignore_js_op>
              <a href="forum.php?mod=attachment&aid=1">115ED2K下载链接.txt</a>
            </ignore_js_op></div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    out = judge_thread_html(
        html,
        board_fid="95",
        list_title="【自转】【百度网盘+115eD2k】示例",
        preferred_link="ed2k",
        forum_id="sehuatang",
        attachments_already_tried=True,
        had_attachments=False,
        attachment_denied=True,
    )
    assert out.verdict == "stub", out.outcome
    assert "无权限" in out.outcome
    assert "蓝奏" not in out.outcome
