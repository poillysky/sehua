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


def test_ed2k_amp_entity_same_uri_deduped():
    """帖内 & 与 &amp; 同链只算 1 条（tid=3443944）。"""
    h = "6F337ED71A359495EFCA91B84B066D74"
    a = f"ed2k://|file|www.98T.la@新:妙手圣医&都市爱之乐章&魔力戒指.mp4|1247685503|{h}|/"
    b = f"ed2k://|file|www.98T.la@新:妙手圣医&amp;都市爱之乐章&amp;魔力戒指.mp4|1247685503|{h}|/"
    links = parse_ed2k_text(a + "\n" + b)
    assert len(links) == 1
    assert "&amp;" not in links[0].link
    assert "&" in links[0].filename


def test_tid3443944_amp_colon_not_false_multi():
    """1V 单文件：&amp; 副本 + 全角/半角冒号名 → 仍单资源，勿 shared_preview。"""
    from db.persist import build_parse_frame, preview_frame_outcome
    from pathlib import Path

    html_path = Path(__file__).resolve().parents[1] / "_tmp_evolve_3443944.html"
    if not html_path.is_file():
        # 最小复现：资源名称两写 + 同 hash 双链
        title = "【自转】【115ED2K】擦边短剧 新：妙手圣医&都市爱之乐章&魔力戒指【1.16G/1V】"
        h = "6F337ED71A359495EFCA91B84B066D74"
        html = f"""
        <html><head><title>{title}</title></head>
        <body>
        <span id="thread_subject">{title}</span>
        <div id="postlist"><div class="t_f" id="postmessage_1">
        【资源名称】：擦边短剧 新：妙手圣医&都市爱之乐章&魔力戒指<br/>
        【资源大小】：1.16G<br/>
        <a href="ed2k://|file|www.98T.la@新:妙手圣医&都市爱之乐章&魔力戒指.mp4|1247685503|{h}|/">ed2k</a>
        ed2k://|file|www.98T.la@新:妙手圣医&amp;都市爱之乐章&amp;魔力戒指.mp4|1247685503|{h}|/
        <img src="https://tu.ewrewej.la/tupian/forum/a.jpg" zoomfile="https://tu.ewrewej.la/tupian/forum/a.jpg" />
        </div></div>
        </body></html>
        """
    else:
        html = html_path.read_text(encoding="utf-8")
        title = "【自转】【115ED2K】擦边短剧 新：妙手圣医&都市爱之乐章&魔力戒指【1.16G/1V】"

    parsed = parse_thread_dual(html, tid=3443944, preferred_link="ed2k", board_fid="103")
    assert len({(a.hash or "").upper() for a in parsed.assets if a.hash}) == 1
    frame = build_parse_frame(parsed, post_title=title)
    assert frame is not None
    assert frame.spec.kind == "single", frame.verdict.tags
    assert len(frame.rows) == 1
    out = preview_frame_outcome(parsed, import_outcome="成功：已提取主链")
    assert out.startswith("成功"), out
    assert "warn:shared_preview" not in frame.verdict.tags
    assert "多资源" not in out


def test_tid3344090_nbsp_uri_not_false_multi():
    """tid=3344090：同 hash 双链仅空格/nbsp 差异 → 单资源，勿预览误报。"""
    from db.persist import (
        _norm_uri_dedupe_key,
        build_parse_frame,
        preview_frame_outcome,
    )

    title = (
        "【自转】【115ED2K】【B站 Yiko湿润兔 咬一口兔娘】2月作品："
        "放课后の归路 JK套装三点式内衣很顶【755m/2v+110p/1配额】"
    )
    h = "F906A787B1A73B02CCD8CE62CF4FA19C"
    u1 = f"ed2k://|file|www.98T.la@Yiko湿润兔 放课后の归路.zip|769134769|{h}|/"
    u2 = f"ed2k://|file|www.98T.la@Yiko湿润兔\xa0\xa0放课后の归路.zip|769134769|{h}|/"
    assert _norm_uri_dedupe_key(u1) == _norm_uri_dedupe_key(u2)

    html = f"""
    <html><head><title>{title}</title></head>
    <body>
    <span id="thread_subject">{title}</span>
    <div id="postlist"><div class="t_f" id="postmessage_1">
    【资源名称】：【B站Yiko湿润兔咬一口兔娘】2月作品：放课后の归路 JK套装三点式内衣很顶<br/>
    【资源名称】：【B站Yiko湿润兔咬一口兔娘】2月作品:放课后の归路 JK套装三点式内衣很顶<br/>
    <a href="{u1}">a</a>
    {u2}
    <img src="https://tu.ewrewej.la/tupian/forum/a.jpg"
         zoomfile="https://tu.ewrewej.la/tupian/forum/a.jpg" />
    </div></div>
    </body></html>
    """
    parsed = parse_thread_dual(html, tid=3344090, preferred_link="ed2k", board_fid="95")
    frame = build_parse_frame(parsed, post_title=title)
    assert frame is not None
    assert frame.spec.kind == "single", frame.verdict.tags
    assert len(frame.rows) == 1
    out = preview_frame_outcome(parsed, import_outcome="成功：已提取主链")
    assert out.startswith("成功"), out
    assert "预览图完全相同" not in out
    assert "链数:1" in out


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
