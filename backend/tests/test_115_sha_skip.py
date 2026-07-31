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

# 色花【sha1】帖 rar 内常见无 115:// 前缀
SAMPLE_115_BARE = (
    "fc3046937.mp4|636932634|"
    "F5D49210FBFBF1473326D911BCFF57C0C8D819AB|"
    "10B8F07E6A5DD161DF9C38047FB6DB8870C7DB22"
)


def test_has_115_sha_link_matches_sample():
    assert has_115_sha_link(SAMPLE_115) is True
    assert has_115_sha_link(f'<div id="postmessage_1">{SAMPLE_115}</div>') is True
    assert has_115_sha_link(SAMPLE_115_MULTILINE) is True
    assert has_115_sha_link(SAMPLE_115_BARE) is True
    assert has_115_sha_link("magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01") is False
    assert has_115_sha_link("115://incomplete") is False


def test_has_115_sha_link_mega_magnet_dump_is_fast():
    """大磁链附件语料不得拖死 has_115_sha_link（曾导致 /health 504）。"""
    import time

    text = "\n".join(
        f"magnet:?xt=urn:btih:{i:040x}&dn=file{i}" for i in range(2000)
    )
    t0 = time.perf_counter()
    assert has_115_sha_link(text) is False
    assert time.perf_counter() - t0 < 0.5


def test_should_skip_as_115sha_only_skips_regex_when_magnet_present():
    from parsers.thread_gates import should_skip_as_115sha_only

    # 磁链 + 伪 115 形态：有 magnet 应直接不跳过，且保持快
    import time

    blob = (
        "magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01\n"
        + ("x|" * 5000)
    )
    t0 = time.perf_counter()
    assert should_skip_as_115sha_only(blob) is False
    assert time.perf_counter() - t0 < 0.2


def test_attach_denied_with_115sha_corpus_stubs_not_115sha_skip():
    """附件无权时即使语料含 115://（115sha），应占位；与文件名是否 115ed2k 无关。"""
    html = """
    <html><head><title>【ED2K】【整理】PKF合集【15V/15配额】 - 论坛</title></head>
    <body>
    <div id="postmessage_1">链接见附件</div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">目录树.txt</a>
      <a href="forum.php?mod=attachment&aid=2">合集 115ed2k.txt</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    html2 = inject_attachment_text(html, SAMPLE_115)
    out = judge_thread_html(
        html2,
        board_fid="95:716",
        forum_id="sehuatang",
        list_title="【ED2K】【整理】PKF合集【15V/15配额】",
        preferred_link="ed2k",
        tid=2543692,
        attachments_already_tried=True,
        attachment_denied=True,
        had_attachments=True,
    )
    assert out.verdict == "stub"
    assert out.outcome == "附件无权（占位入库）"


def test_115ed2k_title_never_counts_as_115sha():
    """【115ed2k】是电驴标，不得按 115sha 标题跳过。"""
    from parsers.thread_gates import (
        title_has_115ed2k_hint,
        title_is_115sha_without_ed2k_magnet,
    )

    assert title_has_115ed2k_hint("【自转】【115eD2k】示例") is True
    assert title_is_115sha_without_ed2k_magnet("【自转】【115eD2k】示例") is False
    assert title_is_115sha_without_ed2k_magnet("【115sha1】【115ed2k】并存") is False
    assert title_is_115sha_without_ed2k_magnet("【115sha1】仅 sha") is True


def test_judge_skips_bare_sha1_attach_corpus():
    """附件解出无协议头 sha1 管线 → 115sha 跳过（勿落成「未解析到」）。"""
    html = """
    <html><head><title>【sha1】(fc3046937) 示例 - 论坛</title></head>
    <body>
    <div id="postmessage_1">【下载地址】：见附件</div>
    <div class="tattl"><ignore_js_op>
      <a href="forum.php?mod=attachment&aid=1">fc3046937.rar</a>
    </ignore_js_op></div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("x" * 15000)
    html2 = inject_attachment_text(html, SAMPLE_115_BARE)
    out = judge_thread_html(
        html2,
        board_fid=104,
        list_title="【sha1】(fc3046937) 示例",
        preferred_link="magnet",
        attachments_already_tried=True,
        had_attachments=True,
    )
    assert out.verdict == "skipped"
    assert "115sha" in out.outcome.lower() or "115" in out.outcome.lower()


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
    assert "115sha" in out.outcome.lower()


def test_title_115sha_only_skips_without_trying_attachments():
    from parsers.thread_gates import title_is_115sha_without_ed2k_magnet

    assert title_is_115sha_without_ed2k_magnet("【115SHA1】欧美合集 37V") is True
    assert title_is_115sha_without_ed2k_magnet("【sha1】(fc3046937) 回収") is True
    assert title_is_115sha_without_ed2k_magnet("【115sha1】【ed2k】合集") is False
    assert title_is_115sha_without_ed2k_magnet("【115eD2k】合集") is False
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
    assert "未解析" in out.outcome


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
    assert "迅雷云盘（跳过）" in out.outcome
    assert out.need_attachments is False


def test_pikpak_share_skips():
    from parsers.thread_gates import has_pikpak_share_link, title_is_pikpak_without_ed2k_magnet

    share = "https://mypikpak.com/s/VOMN-jTAJm2u6wHtQ_XH9SEko1"
    assert has_pikpak_share_link(share) is True
    assert has_pikpak_share_link("mypikpak.com/s/abc_123") is True
    assert title_is_pikpak_without_ed2k_magnet("【整理】【PIKPAK】合集") is True
    assert title_is_pikpak_without_ed2k_magnet("【115eD2k/PIKPAK】合集") is False

    # 纯 PikPak → 网盘跳过
    html = f"""
    <html><head><title>【整理】【PIKPAK】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【整理】【PIKPAK】合集</span>
    <div id="postmessage_1">【资源链接】：{share}</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【整理】【PIKPAK】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "PikPak网盘（跳过）" in out.outcome
    assert out.need_attachments is False

    # 115 与 PikPak 并存 → 不判网盘跳过
    html2 = f"""
    <html><head><title>【整理】【115eD2k/PIKPAK】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【整理】【115eD2k/PIKPAK】合集</span>
    <div id="postmessage_1">先发pikpak的链接。【资源链接】：{share}</div>
    Powered by Discuz!
    </body></html>
    """
    html2 = html2 + ("<!-- pad -->" * 900)
    out2 = judge_thread_html(
        html2,
        board_fid="95:716",
        list_title="【整理】【115eD2k/PIKPAK】合集",
        preferred_link="ed2k",
    )
    # 115 并存：不得标成 PikPak 网盘跳过 / 非资源
    assert "PikPak" not in (out2.outcome or "")
    assert "非资源" not in (out2.outcome or "")


def test_baidu_pan_share_skips():
    from parsers.thread_gates import has_baidu_share_link, title_is_baidu_pan_without_ed2k_magnet

    share = "https://pan.baidu.com/s/1hvdIAh7E16nLaUCgsMONrw?pwd=zqk2"
    assert has_baidu_share_link(share) is True
    assert has_baidu_share_link("pan.baidu.com/s/abc_123") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【自转】【百度网盘】合集") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【百度网盘】【ed2k】合集") is False
    # 裸「百度」「度盘」独占 → 直接百度网盘跳过
    assert title_is_baidu_pan_without_ed2k_magnet("【自转】【百度】合集【10V】") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【度盘】资源合集") is True
    assert title_is_baidu_pan_without_ed2k_magnet("【百度】【115eD2k】合集") is False
    assert title_is_baidu_pan_without_ed2k_magnet("【度盘+磁力】合集") is False

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
    assert "百度网盘（跳过）" in out.outcome
    assert out.need_attachments is False


def test_bare_xunlei_quark_title_skips():
    from parsers.thread_gates import (
        match_skip_cloud_share_title,
        title_is_quark_without_ed2k_magnet,
        title_is_xunlei_cloud_without_ed2k_magnet,
    )

    assert title_is_xunlei_cloud_without_ed2k_magnet("【自转】【迅雷】合集") is True
    assert title_is_xunlei_cloud_without_ed2k_magnet("【迅雷】【ed2k】合集") is False
    assert title_is_xunlei_cloud_without_ed2k_magnet("【迅雷】【magnet】合集") is False
    assert title_is_xunlei_cloud_without_ed2k_magnet("【迅雷】【磁力】合集") is False
    assert title_is_quark_without_ed2k_magnet("【夸克】合集") is True
    assert title_is_quark_without_ed2k_magnet("【夸克】【115】合集") is False
    assert match_skip_cloud_share_title("【百度+夸克】合集") is None
    assert match_skip_cloud_share_title("【迅雷】【百度】合集") is None
    assert match_skip_cloud_share_title("【度盘】【磁链】合集") is None

    html = """
    <html><head><title>【自转】【迅雷】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【迅雷】合集</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">请看网盘</div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【迅雷】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "迅雷" in (out.outcome or "")
    assert out.need_attachments is False


def test_quark_pan_share_skips():
    from parsers.thread_gates import has_quark_share_link, title_is_quark_without_ed2k_magnet

    share = "https://pan.quark.cn/s/a1b2c3d4e5f6"
    assert has_quark_share_link(share) is True
    assert has_quark_share_link("pan.quark.cn/s/abc_123") is True
    assert title_is_quark_without_ed2k_magnet("【夸克网盘】合集") is True
    assert title_is_quark_without_ed2k_magnet("【夸克】【磁力】合集") is False

    html = f"""
    <html><head><title>【自转】【夸克网盘】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【自转】【夸克网盘】合集</span>
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
        list_title="【自转】【夸克网盘】合集",
        preferred_link="magnet",
    )
    assert out.verdict == "skipped"
    assert "夸克网盘（跳过）" in out.outcome
    assert out.need_attachments is False


def test_quark_title_with_txt_attach_skips_without_need_attachments():
    """标题【夸克】+ 附件区 txt：磁力板直接跳过，勿 need_attachments。"""
    html = """
    <html><head><title>【夸克网盘】魔改示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【夸克网盘】魔改示例</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">【资源名称】：demo<br/>【下载地址】：</div>
        <div class="tattl"><ignore_js_op>
          <a href="forum.php?mod=attachment&aid=1">链接.txt</a>
        </ignore_js_op></div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="104",
        list_title="【夸克网盘】魔改示例",
        preferred_link="magnet",
    )
    assert out.verdict == "skipped"
    assert "夸克网盘（跳过）" in out.outcome
    assert out.need_attachments is False


def test_mega_and_gdrive_skip_clear_reason():
    """MEGA / Google 网盘勿落成笼统「非资源帖」。"""
    from parsers.thread_gates import (
        has_gdrive_share_link,
        has_mega_share_link,
        title_is_gdrive_without_ed2k_magnet,
        title_is_mega_without_ed2k_magnet,
    )

    assert has_mega_share_link("https://mega.nz/folder/L0NERCLT#xUQyaEhzOPSLCLEcV8pWBA")
    assert has_gdrive_share_link("https://drive.google.com/file/d/abc/view")
    assert title_is_mega_without_ed2k_magnet("【MEGA】FC2示例") is True
    assert title_is_mega_without_ed2k_magnet("【mg网盘】示例") is True
    # 人名含 mega 子串 ≠ MEGA 网盘
    assert title_is_mega_without_ed2k_magnet(
        "2048独家合集 CB源码直播录屏——meganmeow（260201~260227）合集"
    ) is False
    assert title_is_mega_without_ed2k_magnet(
        "2048独家合集 顶级颜值美腿三开淫骚辣妹Megan_myersss录播合集"
    ) is False
    assert title_is_gdrive_without_ed2k_magnet("[GOOGLE網盤]示例") is True

    html = """
    <html><head><title>【MEGA】示例 - 论坛</title></head>
    <body>
    <span id="thread_subject">【MEGA】示例</span>
    <div id="postlist">
      <div id="post_1">
        <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
        <div id="postmessage_1">
          【下载地址】：https://mega.nz/folder/Abc123#key
        </div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="104",
        list_title="【MEGA】示例",
        preferred_link="magnet",
    )
    assert out.verdict == "skipped"
    assert "MEGA网盘（跳过）" in out.outcome
    assert "非资源" not in out.outcome


def test_extra_cloud_shares_skip_clear_reason():
    """阿里/天翼/123/蓝奏/UC 等扩展网盘：明确跳过，勿「非资源帖」。"""
    from parsers.thread_gates import (
        has_aliyun_share_link,
        has_lanzou_share_link,
        has_pan123_share_link,
        has_tianyi_share_link,
        match_skip_cloud_share_link,
        match_skip_cloud_share_title,
    )

    assert has_aliyun_share_link("https://www.alipan.com/s/abcDEF")
    assert has_tianyi_share_link("https://cloud.189.cn/t/xyz")
    assert has_pan123_share_link("https://www.123pan.com/s/abcd")
    assert has_lanzou_share_link("https://wwasp.lanzoul.com/iakns3n074eh")
    assert match_skip_cloud_share_title("【阿里云盘】合集") is not None
    assert match_skip_cloud_share_title("【123云盘】合集") is not None
    assert match_skip_cloud_share_title("【蓝奏云】工具") is not None
    assert match_skip_cloud_share_link("https://drive.uc.cn/s/xxx").key == "uc"

    cases = [
        ("阿里云盘", "https://www.aliyundrive.com/s/abc123", "阿里"),
        ("123云盘", "https://www.123pan.com/s/abc123", "123"),
        ("蓝奏云", "https://wwasp.lanzoul.com/iakns3n074eh", "蓝奏"),
        ("天翼云盘", "https://cloud.189.cn/t/AbCdEf", "天翼"),
    ]
    for label, url, needle in cases:
        html = f"""
        <html><head><title>【{label}】示例 - 论坛</title></head>
        <body>
        <span id="thread_subject">【{label}】示例</span>
        <div id="postlist">
          <div id="post_1">
            <div class="authi"><em>1#</em><img src="ico_lz.png" alt="楼主"/></div>
            <div id="postmessage_1">下载：{url}</div>
          </div>
        </div>
        Powered by Discuz!
        </body></html>
        """
        html = html + ("<!-- pad -->" * 900)
        out = judge_thread_html(
            html,
            board_fid="104",
            list_title=f"【{label}】示例",
            preferred_link="magnet",
        )
        assert out.verdict == "skipped", (label, out.outcome)
        assert out.outcome == f"{label}（跳过）" or needle in out.outcome, (label, out.outcome)
        assert "非资源" not in out.outcome


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
    # 多种网盘并存 → 归并「非资源（跳过）」，勿失败
    assert "非资源" in out.outcome or "网盘" in out.outcome
    assert out.outcome != "解析入库失败（有链但无主资源）"


def test_incomplete_ed2k_with_baidu_skips_not_failed():
    """正文半截 ed2k（无 hash）+ 百度；标题含 115eD2k → 不判百度网盘，勿失败。"""
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
    assert "百度" not in out.outcome
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
    assert "非资源" in out.outcome or "未解析" in out.outcome
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
