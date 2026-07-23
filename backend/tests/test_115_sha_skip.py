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


def test_judge_115_sha_with_rar_attachment_tries_attachments():
    """正文仅有 115 目录链、附件是 rar：应先下附件（rar 内常有磁力）。"""
    html = f"""
    <html><head><title>【磁力】合集 - 论坛</title></head>
    <body>
    <div id="postmessage_1">
      目录：{SAMPLE_115}<br/>
      【解压密码】：MyBigDick@sehuatang
    </div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">18OnlyGirls.rar</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【磁力】合集",
        preferred_link="magnet",
    )
    assert out.verdict == "need_attachments"
    assert out.need_attachments is True


def test_judge_after_failed_attach_does_not_blame_body_115_as_attach():
    """附件解压失败后，正文 115 目录不应再标成「附件跳过」。"""
    html = f"""
    <html><head><title>【磁力】合集 - 论坛</title></head>
    <body>
    <div id="postmessage_1">目录：{SAMPLE_115}</div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">pack.rar</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    out = judge_thread_html(
        html,
        board_fid=103,
        list_title="【磁力】合集",
        preferred_link="magnet",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "skipped"
    assert "附件" not in out.outcome
    assert "未解析" in out.outcome or "115" in out.outcome


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


def test_title_115sha_only_skips_without_trying_attachments():
    from parsers.thread_gates import title_is_115sha_without_ed2k_magnet

    assert title_is_115sha_without_ed2k_magnet("【115SHA1】欧美合集 37V") is True
    assert title_is_115sha_without_ed2k_magnet("【115sha1】【ed2k】合集") is False
    assert title_is_115sha_without_ed2k_magnet("【磁力】合集") is False

    html = """
    <html><head><title>【115SHA1】欧美4K SheIsNerdy【37V】 - 论坛</title></head>
    <body>
    <div id="postmessage_1">只有预览图，无直链</div>
    <div class="pattl"><ignore_js_op>x</ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    out = judge_thread_html(html, board_fid="141:690", list_title="")
    assert out.verdict == "skipped"
    assert "115sha" in out.outcome.lower() or "115" in out.outcome
    assert out.need_attachments is False


def test_title_115sha_with_ed2k_rar_tries_attachments():
    """标题写 115sha1，但附件是 ed2k.rar → 应先下附件，勿直接跳过。"""
    html = """
    <html><head><title>【自购】【115sha1】示例合集【2V】 - 论坛</title></head>
    <body>
    <div id="postmessage_1">链接见附件</div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">ed2k.rar</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    out = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【自购】【115sha1】示例合集【2V】",
        preferred_link="ed2k",
    )
    assert out.verdict == "need_attachments"
    assert out.need_attachments is True


def test_title_115sha_after_attach_ed2k_imports():
    """115sha 标题帖：附件注入 ed2k 后应入库，不再按标题跳过。"""
    html = """
    <html><head><title>【115sha1】示例合集 - 论坛</title></head>
    <body>
    <div id="postmessage_1">见附件</div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">ed2k.rar</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    ed2k = (
        "ed2k://|file|ppv-orimrs526.mp4|717742734|"
        "D8474F7BE71FDFB00A5F9B9F7AA7CD16|/"
    )
    merged = inject_attachment_text(html, ed2k)
    out = judge_thread_html(
        merged,
        board_fid="141:690",
        list_title="【115sha1】示例合集",
        preferred_link="ed2k",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "import"
    assert out.parsed is not None
    assert out.parsed.ed2k_links


def test_no_ed2k_magnet_after_attach_try_skips():
    html = """
    <html><head><title>资源合集 98T - 论坛</title></head>
    <body>
    <div id="postmessage_1">见附件</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    out = judge_thread_html(
        html,
        board_fid=36,
        list_title="资源合集",
        attachments_already_tried=True,
        had_attachments=False,
    )
    assert out.verdict == "skipped"
    assert "ed2k" in out.outcome or "磁力" in out.outcome


def test_has_115_share_link_and_import():
    from parsers.thread_gates import has_115_share_link, title_is_115_share_without_ed2k_magnet

    share = "https://115.com/s/swz25fy36lg?password=xfa8#"
    assert has_115_share_link(share) is True
    assert has_115_share_link("115.com/s/abc123") is True
    assert has_115_share_link("https://115cdn.com/s/swf6jpt3ngd?password=1122") is True
    assert has_115_share_link(SAMPLE_115) is False
    assert title_is_115_share_without_ed2k_magnet("「115分享链接」异形合集") is True
    assert title_is_115_share_without_ed2k_magnet("【115网盘分享+百度网盘分享】游戏") is True
    assert title_is_115_share_without_ed2k_magnet("【115分享码】合集") is True
    assert title_is_115_share_without_ed2k_magnet("【115分享】【ed2k】合集") is False

    html = f"""
    <html><head><title>「115分享链接」异形合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">「115分享链接」异形合集</span>
    <div id="postmessage_1">115链接：{share}</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="「115分享链接」异形合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.link_kind == "115share"
    assert out.need_attachments is False


def test_115cdn_share_with_access_code_imports():
    share = "https://115cdn.com/s/swf6jpt3ngd?password=1122#"
    html = f"""
    <html><head><title>【整理】【115网盘分享+百度网盘分享】游戏【2G】 - 论坛</title></head>
    <body>
    <span id="thread_subject">【整理】【115网盘分享+百度网盘分享】游戏【2G】</span>
    <div id="postmessage_1">
      【资源链接】：{share}<br/>
      115访问码：1122<br/>
      百度网盘：https://pan.baidu.com/s/1abcDEF?pwd=wwpa
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【整理】【115网盘分享+百度网盘分享】游戏【2G】",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.link_kind == "115share"
    assert out.parsed is not None
    assert out.parsed.extract_password == "1122"
    assert out.need_attachments is False


def test_xunlei_cloud_share_skips():
    from parsers.thread_gates import has_xunlei_share_link, title_is_xunlei_cloud_without_ed2k_magnet

    share = "https://pan.xunlei.com/s/VOClhLBDZ8kGIAKZSmSQ2Q4WA1#"
    assert has_xunlei_share_link(share) is True
    assert has_xunlei_share_link("pan.xunlei.com/s/abc_123") is True
    assert title_is_xunlei_cloud_without_ed2k_magnet("【自转】【迅雷云盘】合集【149V/115G】") is True
    assert title_is_xunlei_cloud_without_ed2k_magnet("【迅雷云盘】【ed2k】合集") is False

    html = f"""
    <html><head><title>【自转】【迅雷云盘】合集【149V/115G】 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【迅雷云盘】合集【149V/115G】</span>
    <div id="postmessage_1">资源：{share}</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【迅雷云盘】合集【149V/115G】",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "迅雷云盘" in out.outcome
    assert out.need_attachments is False


def test_pikpak_share_skips():
    from parsers.thread_gates import has_pikpak_share_link, title_is_pikpak_without_ed2k_magnet

    share = "https://mypikpak.com/s/VOMN-jTAJm2u6wHtQ_XH9SEko1"
    assert has_pikpak_share_link(share) is True
    assert has_pikpak_share_link("mypikpak.com/s/abc_123") is True
    assert title_is_pikpak_without_ed2k_magnet("【整理】【PIKPAK】合集") is True
    assert title_is_pikpak_without_ed2k_magnet("【115eD2k/PIKPAK】合集") is False

    html = f"""
    <html><head><title>【整理】【115eD2k/PIKPAK】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【整理】【115eD2k/PIKPAK】合集</span>
    <div id="postmessage_1">先发pikpak的链接。【资源链接】：{share}</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【整理】【115eD2k/PIKPAK】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "PikPak" in out.outcome
    assert out.need_attachments is False


def test_baidu_pan_share_skips():
    from parsers.thread_gates import has_baidu_share_link, title_is_baidu_pan_without_ed2k_magnet

    share = "https://pan.baidu.com/s/1hvdIAh7E16nLaUCgsMONrw?pwd=zqk2"
    assert has_baidu_share_link(share) is True
    assert has_baidu_share_link("pan.baidu.com/s/abc_123") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【自转】【百度网盘】合集") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【百度网盘】【ed2k】合集") is False

    html = f"""
    <html><head><title>【自转】【百度网盘】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【百度网盘】合集</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">资源：{share}</div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【百度网盘】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "百度网盘" in out.outcome
    assert out.need_attachments is False


def test_reply_baidu_does_not_skip_lz_ed2k_attachment():
    """回帖贴百度封面链，楼主有 ed2k.zip 附件 → 应先下附件，勿百度跳过。"""
    html = """
    <html><head><title>【自整理合集】【ed2k】示例合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自整理合集】【ed2k】示例合集</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">链接见附件 ed2k.zip</div>
        <div class="tattl"><ignore_js_op>
          <a href="forum.php?mod=attachment&aid=1">demo_ed2k.zip</a>
        </ignore_js_op></div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">
          封面：https://pan.baidu.com/s/1wTbr2pUU-P1cRWmHNLxf5Q?pwd=qnkb
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="141:691",
        list_title="【自整理合集】【ed2k】示例合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "need_attachments"
    assert out.need_attachments is True
    assert "百度" not in out.outcome


def test_baidu_op_not_failed_by_reply_magnet():
    """楼主仅百度/迅雷网盘，回帖有人贴磁力 → 应按网盘跳过，勿「有链但无主资源」失败。"""
    html = """
    <html><head><title>【自转】【百度云盘+迅雷云盘】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【百度云盘+迅雷云盘】示例</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">
          【资源名称】：demo<br>
          百度：https://pan.baidu.com/s/1MRoPSDL3UBxQ7TDjNGeeFw?pwd=cgvb<br>
          迅雷：https://pan.xunlei.com/s/VOPiNj7JQOdVHsoV-juqILVyA1#
        </div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">
          需要那么麻烦？直接链接秒就是
          magnet:?xt=urn:btih:4801A7C1B020F7B75346A5F96EDD1AE9993C59DD
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【百度云盘+迅雷云盘】示例",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "网盘" in out.outcome or "百度" in out.outcome or "迅雷" in out.outcome
    assert out.outcome != "解析入库失败（有链但无主资源）"


def test_incomplete_ed2k_with_baidu_skips_not_failed():
    """正文半截 ed2k（无 hash）+ 百度网盘 → 网盘跳过，勿失败。"""
    html = """
    <html><head><title>【自转】【百度/115eD2k】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【百度/115eD2k】示例</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">
          【资源名称】：demo<br>
          百度：https://pan.baidu.com/s/1COXim2I4c7t3FjYO5i5rsQ?pwd=7ryv<br>
          ed2k://|file|www.98T.la@demo.zip|509285037|<br>
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【百度/115eD2k】示例",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "百度" in out.outcome or "网盘" in out.outcome
    assert out.outcome != "解析入库失败（有链但无主资源）"


def test_discussion_op_skips_despite_reply_ed2k():
    """楼主讨论帖无资源，回帖有人贴 ed2k → 非资源跳过，勿失败。"""
    html = """
    <html><head><title>欧美媚黑熟女系列推荐 - 论坛</title></head>
    <body>
    <span id="thread_subject">欧美媚黑熟女系列推荐</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">
          第一次接触媚黑是blacked，推荐喜欢黑白配的兄弟站内搜索。
          后面我打算整理一个帖子，大家也可以跟帖推荐。
        </div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">
          推荐一个
          <a href="ed2k://|file|www.98T.la@OnlyFansPUNA.mp4|6785740173|07B21C098E471B87E16590310F5491F9|/">
            www.98T.la@OnlyFansPUNA.mp4
          </a>
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="欧美媚黑熟女系列推荐",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "非资源" in out.outcome or "未发现" in out.outcome or "无目标" in out.outcome
    assert out.outcome != "解析入库失败（有链但无主资源）"


def test_reply_115sha_ignored_when_lz_has_ed2k():
    """回帖贴 115sha，楼主正文有 ed2k → 应入库，勿 115sha 跳过。"""
    ed2k = (
        "ed2k://|file|demo.mkv|123456|"
        "0123456789ABCDEF0123456789ABCDEF|/"
    )
    html = f"""
    <html><head><title>【ed2k】示例资源 - 论坛</title></head>
    <body>
    <span id="thread_subject">【ed2k】示例资源</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">资源：{ed2k}</div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">{SAMPLE_115}</div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【ed2k】示例资源",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert "115sha" not in out.outcome


def test_reply_please_reply_marker_ignored():
    """回帖复读「请回复」，楼主已公开资源 → 勿判需回复贴。"""
    from parsers.thread_gates import is_reply_required_post, post_text

    ed2k = (
        "ed2k://|file|demo.mkv|123456|"
        "0123456789ABCDEF0123456789ABCDEF|/"
    )
    html = f"""
    <html><head><title>【ed2k】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【ed2k】示例</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">资源：{ed2k}</div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">
          引用：游客，如果您要查看本帖隐藏内容请回复
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    assert is_reply_required_post(html) is False
    assert "请回复" not in post_text(html)
    assert "demo.mkv" in post_text(html)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【ed2k】示例",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"


def test_reply_magnet_blockcode_not_imported():
    """回帖 blockcode 磁力，楼主无链 → 勿从回帖入库。"""
    from parsers.links import parse_thread_dual

    magnet = "magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01"
    html = f"""
    <html><head><title>讨论帖 - 论坛</title></head>
    <body>
    <span id="thread_subject">随便聊聊</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">求资源，有没有人发一下</div>
      </div>
      <div id="post_2">
        <div class="authi"><em>2#</em></div>
        <div id="postmessage_2">
          <div class="blockcode"><ol><li>{magnet}</li></ol></div>
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    parsed = parse_thread_dual(html, preferred_link="magnet")
    assert parsed.primary_link_kind == "none"
    assert not parsed.magnets
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="36",
        list_title="随便聊聊",
        preferred_link="magnet",
    )
    assert out.verdict == "skipped"
    assert out.verdict != "import"
