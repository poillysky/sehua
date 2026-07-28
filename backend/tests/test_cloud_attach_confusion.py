"""易混淆误判：标题写 115eD2k，正文夹带蓝奏推广链时，勿判网盘跳过。"""

from __future__ import annotations

from parsers.thread_gates import (
    match_skip_cloud_share_link,
    match_skip_cloud_share_title,
    title_has_target_or_115_hint,
)
from workers.thread_outcome import judge_thread_html


def _pad(html: str) -> str:
    return html + ("<!-- pad -->" * 900)


def test_title_only_one_cloud_skips():
    assert match_skip_cloud_share_title("【夸克网盘】合集") is not None
    assert match_skip_cloud_share_title("【夸克网盘】合集").key == "quark"


def test_title_115_with_baidu_not_cloud():
    """标题 115+百度并存 → 不判网盘。"""
    assert match_skip_cloud_share_title("【自转】【百度网盘+115eD2k】示例") is None
    assert match_skip_cloud_share_title("【百度网盘+115】合集") is None
    assert title_has_target_or_115_hint("【百度网盘+115eD2k】示例") is True


def test_title_115g_capacity_not_115_hint():
    """容量 115G 不是 115 资源暗示。"""
    assert title_has_target_or_115_hint("【迅雷云盘】合集【149V/115G】") is False
    assert match_skip_cloud_share_title("【自转】【迅雷云盘】合集【149V/115G】") is not None


def test_title_two_clouds_not_exclusive():
    assert match_skip_cloud_share_title("【百度网盘+夸克】合集") is None


def test_resource_links_only_baidu_skips():
    assert match_skip_cloud_share_link("见：https://pan.baidu.com/s/1abcXYZ").key == "baidu"


def test_resource_115_and_baidu_not_cloud():
    blob = (
        "https://115.com/s/abc123\n"
        "https://pan.baidu.com/s/1abcXYZ\n"
    )
    assert match_skip_cloud_share_link(blob) is None


def test_resource_ed2k_and_baidu_not_cloud():
    blob = (
        "ed2k://|file|a.mkv|1|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/\n"
        "https://pan.baidu.com/s/1abcXYZ\n"
    )
    assert match_skip_cloud_share_link(blob) is None


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
    assert "百度" not in (out.outcome or "")


def test_body_lanzou_promo_alone_with_115_title_not_lanzou_skip():
    """标题有 115，正文只有蓝奏推广链 → 不因正文判蓝奏。"""
    html = _pad(
        """
        <html><head><title>【整理】【115eD2k】示例 - 论坛</title></head>
        <body>
        <span id="thread_subject">【整理】【115eD2k】示例</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">
              https://wwsx.lanzouw.com/iZq9b35t2p2h
            </div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    out = judge_thread_html(
        html,
        board_fid="95",
        list_title="【整理】【115eD2k】示例",
        preferred_link="ed2k",
        forum_id="sehuatang",
    )
    assert "蓝奏" not in (out.outcome or ""), out.outcome


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


def test_tid3341941_115_denied_baidu_txt_not_lanzou_skip():
    """115 附件无权、只注入百度口令 → stub，勿标蓝奏（回归 tid=3341941）。"""
    from parsers.attachments import inject_attachment_text

    html = _pad(
        """
        <html><head><title>【自转】【百度网盘+115eD2k】汐梦瑶示例 - 论坛</title></head>
        <body>
        <span id="thread_subject">【自转】【百度网盘+115eD2k】汐梦瑶示例</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">
              安卓手机可以下载这个： https://wwsx.lanzouw.com/iZq9b35t2p2h 密码:fwnu
            </div>
            <div class="tattl"><ignore_js_op>
              <a href="forum.php?mod=attachment&aid=1">115防失效备用版.txt</a>
              <a href="forum.php?mod=attachment&aid=2">百度网盘防失效备用版.txt</a>
            </ignore_js_op></div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
    )
    baidu_only = (
        "复制口令后打开「手机百度网盘 App」即可\n"
        "墀垩创街忐了心凉礼艇左凿圜\n"
        "【解压密码】：www.98T.la@\n"
    )
    html2 = inject_attachment_text(html, baidu_only)
    out = judge_thread_html(
        html2,
        board_fid="95",
        list_title="【自转】【百度网盘+115eD2k】汐梦瑶示例",
        preferred_link="ed2k",
        forum_id="sehuatang",
        attachments_already_tried=True,
        had_attachments=True,
        attachment_denied=True,
    )
    assert out.verdict == "stub", out.outcome
    assert "无权限" in out.outcome
    assert "蓝奏" not in out.outcome
