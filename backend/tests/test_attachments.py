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
