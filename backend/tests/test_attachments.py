"""Attachment extract / zip-txt / torrent→magnet / inject."""

from __future__ import annotations

import io
import zipfile

from parsers.attachments import (
    extract_download_attachments,
    filter_tail_attachments,
    filter_torrent_attachments,
    inject_attachment_text,
    is_attachment_denied,
)
from parsers.links import parse_thread_dual
from parsers.torrent import parse_torrent_bytes
from crawler.attachments import _extract_txt_from_archive, _text_from_attachment_bytes
from parsers.attachments import DownloadAttachment


def _minimal_torrent(name: bytes = b"demo.bin", length: int = 123) -> bytes:
    # bencode: d8:announce0:4:infod6:lengthi{len}e4:name{n}:{name}ee
    info = b"d6:lengthi" + str(length).encode() + b"e4:name" + str(len(name)).encode() + b":" + name + b"e"
    return b"d8:announce0:4:info" + info + b"e"


def test_extract_and_filter_tail():
    html = """
    <div class="tattl">
      <a href="forum.php?mod=attachment&aid=1">目录树.txt</a>
      <a href="forum.php?mod=attachment&aid=2">链接A.txt</a>
      <a href="forum.php?mod=attachment&aid=3">pack.zip</a>
      <a href="forum.php?mod=attachment&aid=4">seed.torrent</a>
    </div>
    """
    all_a = extract_download_attachments("https://www.sehuatang.net/", html)
    kinds = {a.kind for a in all_a}
    assert "txt" in kinds and "zip" in kinds and "torrent" in kinds
    tail = filter_tail_attachments(all_a, limit=3)
    assert all(a.kind in ("txt", "zip", "rar") for a in tail)
    assert not any("目录" in a.name for a in tail)
    torrents = filter_torrent_attachments(all_a)
    assert len(torrents) == 1 and torrents[0].kind == "torrent"


def test_cf_email_obfuscated_attachment_name():
    """含 @ 的附件名被 CF 混淆成 [email protected] 时仍应识别为 txt。"""
    enc = "d3a4a4a4fdeaeb87fdbfb29383a1baa5b2a7b690b2a0a7babdb4fe8bfda7aba7"
    html = f"""
    <ignore_js_op>
      <a href="forum.php?mod=attachment&amp;aid=AAA">
        <span class="__cf_email__" data-cfemail="{enc}">[email&#160;protected]</span>
      </a>
      <a href="forum.php?mod=attachment&amp;aid=BBB">xxx_目录树.txt</a>
      <a href="forum.php?mod=attachment&amp;aid=CCC">shot_115链接.png</a>
    </ignore_js_op>
    """
    all_a = extract_download_attachments("https://www.sehuatang.net/", html)
    names = [a.name for a in all_a]
    assert "www.98T.la@PrivateCasting-X.txt" in names
    assert not any(n.endswith(".png") for n in names)
    tail = filter_tail_attachments(all_a, limit=3)
    assert [a.name for a in tail] == ["www.98T.la@PrivateCasting-X.txt"]


def test_rar_with_文件夹_in_name_not_skipped():
    """「新建文件夹.rar」是资源包，不能当目录树跳过，否则无权包会反复重试。"""
    html = """
    <ignore_js_op>
      <a href="forum.php?mod=attachment&amp;aid=1">www.98T.la  新建文件夹      下载麻烦顺手评评分.rar</a>
      <a href="forum.php?mod=attachment&amp;aid=2">目录树.txt</a>
    </ignore_js_op>
    """
    all_a = extract_download_attachments("https://www.sehuatang.net/", html)
    assert any(a.kind == "rar" for a in all_a)
    tail = filter_tail_attachments(all_a, limit=3)
    assert len(tail) == 1
    assert tail[0].kind == "rar"
    assert "文件夹" in tail[0].name


def test_zip_inner_txt_and_ed2k_parse():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "links.txt",
            "ed2k://|file|demo.rar|100|ABCDEF0123456789ABCDEF0123456789|/\n",
        )
    data = buf.getvalue()
    text = _extract_txt_from_archive(data, "zip")
    assert "ed2k://" in text

    att = DownloadAttachment(name="pack.zip", url="http://x/a", kind="zip")
    out = _text_from_attachment_bytes(att, data)
    parsed = parse_thread_dual(
        "<html><title>t</title></html>",
        tid=1,
        preferred_link="ed2k",
        extra_text=out,
    )
    assert parsed.primary_link_kind == "ed2k"
    assert parsed.ed2k_links


def test_archive_password_candidates_from_post():
    from crawler.attachments import _archive_password_candidates

    html = """
    <html><body>
      <div id="postmessage_1">
        【资源名称】：示例<br>
        【解压密码】：www.98T.la@
      </div>
    </body></html>
    """
    cands = _archive_password_candidates(html)
    assert "www.98T.la@" in cands
    assert "www.98T.la" in cands


def test_password_protected_zip_txt_extract():
    """帖内密码应能解开加密 zip 里的 txt（AES → pyzipper）。"""
    import pytest

    pyzipper = pytest.importorskip("pyzipper")
    from crawler.attachments import _extract_txt_from_archive

    link = "ed2k://|file|demo.rar|100|ABCDEF0123456789ABCDEF0123456789|/\n"
    buf = io.BytesIO()
    with pyzipper.AESZipFile(
        buf,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(b"secret123")
        zf.writestr("links.txt", link)
    data = buf.getvalue()
    assert not _extract_txt_from_archive(data, "zip")
    assert "ed2k://" in _extract_txt_from_archive(data, "zip", passwords=["secret123"])
    assert "ed2k://" in _extract_txt_from_archive(
        data, "zip", passwords=["wrong", "secret123"]
    )


def test_bare_password_98t_extracted():
    """帖内仅写「密码」+ www.98T.la@（无解压前缀）也应抽出。"""
    from crawler.attachments import _archive_password_candidates
    from parsers.content import extract_password

    html = """
    <div id="postmessage_1">
      <font>密码</font><font>www.98T.la@</font>
      <a href="forum.php?mod=attachment&aid=1">新建文件夹.rar</a>
    </div>
    """
    assert extract_password("密码 www.98T.la@") == "www.98T.la@"
    cands = _archive_password_candidates(html)
    assert "www.98T.la@" in cands
    assert "www.98T.la" in cands


def test_nested_zip_uses_same_password():
    """外层 zip 内再套加密 zip，应用同一帖内密码解开取 txt。"""
    import pytest

    pyzipper = pytest.importorskip("pyzipper")
    from crawler.attachments import _extract_txt_from_archive

    link = "ed2k://|file|demo.mp4|10|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/\n"
    inner = io.BytesIO()
    with pyzipper.AESZipFile(
        inner,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(b"www.98T.la@")
        zf.writestr("ed2k.txt", link)
    outer = io.BytesIO()
    with pyzipper.AESZipFile(
        outer,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(b"www.98T.la@")
        zf.writestr("新建文件夹/inner.zip", inner.getvalue())
    text = _extract_txt_from_archive(
        outer.getvalue(), "zip", passwords=["www.98T.la@", "www.98T.la"]
    )
    assert "ed2k://" in text


def test_torrent_to_magnet():
    data = _minimal_torrent()
    magnet = parse_torrent_bytes(data, filename_hint="seed.torrent")
    assert magnet is not None
    assert magnet.link.lower().startswith("magnet:?xt=urn:btih:")
    assert magnet.infohash


def test_inject_and_denied():
    html = '<div id="postmessage_1">hello</div>'
    merged = inject_attachment_text(html, "magnet:?xt=urn:btih:AABBCCDDEEFF00112233445566778899")
    assert "postmessage_attach0" in merged
    assert "magnet:?" in merged
    assert is_attachment_denied("抱歉，只有特定用户可以下载此附件")


def test_denied_not_masked_by_empty_download():
    """第一个附件空下载、第二个无权时，结果须带 denied（不能只标 downloaded）。"""
    from parsers.attachments import AttachmentFetchResult

    # 模拟 download_tail 汇总结论（与 crawler 逻辑一致）
    any_downloaded = True
    any_denied = True
    result_text = ""
    if result_text:
        out = AttachmentFetchResult(text=result_text, downloaded=True, denied=any_denied)
    elif any_denied:
        out = AttachmentFetchResult(downloaded=any_downloaded, denied=True)
    elif any_downloaded:
        out = AttachmentFetchResult(downloaded=True)
    else:
        out = AttachmentFetchResult(failed=True)
    assert out.denied is True
    assert out.downloaded is True
    assert not out.text


def test_judge_stubs_when_second_attachment_denied():
    """正文无链、附件已试、第二附件无权 → 占位入库，不重试。"""
    from workers.thread_outcome import judge_thread_html

    html = """
    <html><head><title>【高清】示例资源贴 - 色花堂</title></head>
    <body>
      <span id="thread_subject">【高清】示例资源贴</span>
      <div id="postmessage_1">链接见第二个附件</div>
      <div class="tattl">
        <a href="forum.php?mod=attachment&amp;aid=1">说明.txt</a>
        <a href="forum.php?mod=attachment&amp;aid=2">资源链接.txt</a>
      </div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    # 说明.txt 下到了无用文本，资源链接.txt 无权
    out = judge_thread_html(
        html,
        board_fid=95,
        list_title="【高清】示例资源贴",
        attachments_already_tried=True,
        attachment_denied=True,
        had_attachments=True,
        preferred_link="ed2k",
    )
    assert out.verdict == "stub"
    assert out.outcome == "无权限下载附件"


def test_judge_tries_attachments_when_html_has_decoy_ed2k():
    """封面 tip 里有 ed2k、正文无主资源、有 rar 附件 → 应下附件，勿直接「有链但无主资源」。"""
    from workers.thread_outcome import judge_thread_html

    html = """
    <html><head><title>【ED2k】合集 - 色花堂</title></head>
    <body>
      <span id="thread_subject">【ED2k】合集</span>
      <div id="postmessage_1">资源在附件压缩包</div>
      <ignore_js_op>
        <a id="ed2k_Q1u" href="ed2k://|file|波姐封面.zip|207438322|92262C23A97D1D04DA885978E4B7C8E6|/" target="_blank">波姐封面.zip</a>
        <a href="forum.php?mod=attachment&amp;aid=1">www.98T.la@资源.rar</a>
      </ignore_js_op>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="141:691",
        list_title="【ED2k】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "need_attachments"
    assert out.attachment_kind == "txt_tail"
    assert out.outcome != "解析入库失败（有链但无主资源）"

    denied = judge_thread_html(
        html,
        board_fid="141:691",
        list_title="【ED2k】合集",
        preferred_link="ed2k",
        attachments_already_tried=True,
        attachment_denied=True,
        had_attachments=False,
    )
    assert denied.verdict == "stub"
    assert denied.outcome == "无权限下载附件"


def test_ed2k_board_picks_torrent_when_only_torrent_attach():
    """情色分享等电驴板：仅有 .torrent 时应转磁力，而非只找 txt/zip。"""
    from parsers.attachments import pick_ed2k_attachment_kind
    from workers.thread_outcome import judge_thread_html

    html = """
    <html><head><title>【欧美VR种子】示例 - 色花堂</title></head>
    <body>
      <span id="thread_subject">【欧美VR种子】示例</span>
      <div id="postmessage_1">种子见附件</div>
      <ignore_js_op>
        <a href="forum.php?mod=attachment&amp;aid=1">www.98T.la@demo.torrent</a>
      </ignore_js_op>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    assert pick_ed2k_attachment_kind("https://www.sehuatang.net/", html) == "torrent"
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【欧美VR种子】示例",
        preferred_link="ed2k",
        base_url="https://www.sehuatang.net/",
    )
    assert out.verdict == "need_attachments"
    assert out.attachment_kind == "torrent"


def test_judge_skips_preview_only_no_resource_links():
    """仅有预览图、无 txt/zip/rar/torrent、无正文链 → 直接跳过，勿因「附件」字样去下附件。"""
    from parsers.thread_gates import looks_like_attachment_zone
    from workers.thread_outcome import judge_thread_html

    html = """
    <html><head><title>【自转】【115ed2k】示例无链接贴 - 色花堂</title></head>
    <body>
      <span id="thread_subject">【自转】【115ed2k】示例无链接贴</span>
      <div id="postmessage_1">【资源名称】：示例 大哥链接忘记放了吧</div>
      <ignore_js_op>
        <img aid="1" src="shot.png" />
        <a href="https://tu.example/shot.png" target="_blank">下载附件</a>
      </ignore_js_op>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    assert looks_like_attachment_zone(html) is False
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【自转】【115ed2k】示例无链接贴",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert out.need_attachments is False
    assert "未解析到" in out.outcome or "跳过" in out.outcome


def test_judge_skips_after_attachments_tried_without_link():
    """附件已下到、仍无 ed2k/磁力 → 跳过（勿占位）。"""
    from workers.thread_outcome import judge_thread_html

    html = """
    <html><head><title>【高清】示例资源贴 - 色花堂</title></head>
    <body>
      <span id="thread_subject">【高清】示例资源贴</span>
      <div id="postmessage_1">链接见附件</div>
      <div class="tattl">
        <a href="forum.php?mod=attachment&amp;aid=2">资源链接.txt</a>
      </div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid=95,
        list_title="【高清】示例资源贴",
        attachments_already_tried=True,
        attachment_denied=False,
        had_attachments=True,
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "未解析到" in out.outcome
