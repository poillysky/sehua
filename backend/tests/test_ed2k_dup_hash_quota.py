"""同 hash 不同文件名的 ed2k 应计为多配额份，勿 hash 去重成漏链。"""

from __future__ import annotations

from db.persist import preview_frame_outcome
from parsers.attachments import inject_attachment_text
from parsers.ed2k import parse_ed2k_text
from parsers.links import parse_thread_dual


def test_same_hash_different_filename_kept_for_quota():
    """tid=3524065：4 条链里首尾同 hash 不同名 → 仍计 4，对照 4配额。"""
    h = "69FD2EB08E6C14674C3AA18758C5BC3B"
    text = "\n".join(
        [
            f"ed2k://|file|www.98T.la@_a_#x_2.mp4|1570168919|{h}|/",
            f"ed2k://|file|www.98T.la@_a_#x_2_1.mp4|338927148|00298BA08BECD77375BD6E065A215210|/",
            f"ed2k://|file|www.98T.la@_a_#x_2_2.mp4|831241127|9C02C7EA266F56C1528EE980E79461D2|/",
            f"ed2k://|file|www.98T.la@_a_#x_2_3.mp4|1570168919|{h}|/",
        ]
    )
    links = parse_ed2k_text(text)
    assert len(links) == 4
    assert links[0].hash == links[3].hash
    assert links[0].filename != links[3].filename


def test_exact_duplicate_ed2k_still_deduped():
    h = "69FD2EB08E6C14674C3AA18758C5BC3B"
    line = f"ed2k://|file|same.mp4|100|{h}|/"
    assert len(parse_ed2k_text(line + "\n" + line)) == 1


def test_tid3524065_quota4_not_undercount():
    title = "【自转】【115eD2k+百度】绿播女神下海！超级漂亮~【囡囡儿】敏感体质 跳蛋喷水 【4GB/4V/4配额】"
    h = "69FD2EB08E6C14674C3AA18758C5BC3B"
    attach = "\n".join(
        [
            f"ed2k://|file|www.98T.la@_绿播_#囡囡儿_2.mp4|1570168919|{h}|/",
            f"ed2k://|file|www.98T.la@_绿播_#囡囡儿_2_1.mp4|338927148|00298BA08BECD77375BD6E065A215210|/",
            f"ed2k://|file|www.98T.la@_绿播_#囡囡儿_2_2.mp4|831241127|9C02C7EA266F56C1528EE980E79461D2|/",
            f"ed2k://|file|www.98T.la@_绿播_#囡囡儿_2_3.mp4|1570168919|{h}|/",
        ]
    )
    html = f"""
    <html><head><title>{title}</title></head>
    <body><span id="thread_subject">{title}</span>
    <td class="t_f">正文无链</td></body></html>
    """
    html2 = inject_attachment_text(html, attach)
    parsed = parse_thread_dual(
        html2,
        tid=3524065,
        preferred_link="ed2k",
        extra_text=attach,
        base_url="https://www.sehuatang.net/thread-3524065-1-1.html",
        board_fid="95:716",
    )
    parsed.had_attachments = True
    assert len(parsed.assets) == 4
    out = preview_frame_outcome(parsed, import_outcome="成功：附件解析出目标链接")
    assert out.startswith("成功"), out
    assert "链数:4" in out
    assert "漏链" not in out
