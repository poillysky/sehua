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
    <div id="postmessage_1">资源：{share}</div>
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
