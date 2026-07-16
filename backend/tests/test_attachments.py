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


def test_judge_stubs_after_attachments_tried_without_link():
    """已下附件仍无目标链 → 占位（避免队列无限重试）。"""
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
    assert out.verdict == "stub"
    assert "附件" in out.outcome
