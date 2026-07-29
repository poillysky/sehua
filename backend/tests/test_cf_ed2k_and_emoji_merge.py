# -*- coding: utf-8 -*-
"""CF 脏 ed2k 文件名过滤；⚠/⚠️ 近同名合并。"""

from __future__ import annotations

from parsers.ed2k import parse_ed2k_text
from parsers.links import DualParseResult, ParsedAsset, build_assets
from db.persist import _merge_truncated_name_groups, _names_emoji_equivalent


def test_poisoned_cf_ed2k_filename_dropped():
    blob = (
        "ed2k://|file|www.98T.la@BOKU-001.mp4|3903884778|B129185048D95C0368E58DBA318F9DA9|/\n"
        'ed2k://|file|<a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
        'data-cfemail="1562">[email&#160;protected]</a>|3903884778|B129185048D95C0368E58DBA318F9DA9|/\n'
        "ed2k://|file|www.98T.la@BOKU-002.mp4|3381322775|C3588D963BB30B1ED314E5B80CD173BD|/\n"
    )
    links = parse_ed2k_text(blob)
    assert len(links) == 2
    names = {x.filename for x in links}
    assert "www.98T.la@BOKU-001.mp4" in names
    assert "www.98T.la@BOKU-002.mp4" in names
    assert not any("<" in x.filename for x in links)


def test_cf_email_inside_bbcode_url_ed2k_recovered():
    """tid=3219637：blockcode 里 ed2k 文件名被 [url]+CF 邮件保护包住，不得整链丢弃。"""
    from parsers.content import decode_cf_email
    from parsers.links import parse_thread_dual

    enc = "334444441d0a0b671d5f52730201010a01061e0303021e7072617a711d5e4307"
    assert decode_cf_email(enc) == "www.98T.la@122925-001-CARIB.mp4"
    blob = (
        'ed2k://|file|[url]<a href="/cdn-cgi/l/email-protection" class="__cf_email__" '
        f'data-cfemail="{enc}">[email&#160;protected]</a>[/url]'
        "|1653909041|9173C167BC2F0D3378FD2457500F050B|/"
    )
    links = parse_ed2k_text(blob)
    assert len(links) == 1
    assert links[0].filename == "www.98T.la@122925-001-CARIB.mp4"
    assert links[0].hash == "9173C167BC2F0D3378FD2457500F050B"
    assert links[0].size == 1653909041

    html = f"""
    <span id="thread_subject">【自转】【115ED2K】加勒比【1V/1.54G】</span>
    <td id="postmessage_1">
    <div class="blockcode"><div id="code_X"><ol><li>{blob}</ol></div></div>
    </td>
    """
    dual = parse_thread_dual(html, tid=3219637)
    assert len(dual.assets) >= 1
    assert any(a.hash.upper() == "9173C167BC2F0D3378FD2457500F050B" for a in dual.assets)


def test_discuz_html_poisoned_ed2k_salvaged():
    """tid=3405418：Discuz 把含 @ 的 ed2k 渲成嵌套 <a>/script，|size|hash| 仍在。"""
    blob = (
        'ed2k://|file|<a href="http://www.98T.la@初夏1.rar" target="_blank">'
        "www.98T.la@初夏1.rar[/\" target=\"_blank\">[url]www.98T.la@初夏1.rar[ (0 Bytes)</a>"
        "<script language=\"javascript\">$('ed2k_T5n').innerHTML=htmlspecialchars("
        "unescape(decodeURIComponent('[url]www.98T.la@初夏1.rar[')))+' (0 Bytes)';"
        "</script>url]|976158193|B9DF3760FC34EEB3F7A14352325CF7C7|/"
    )
    links = parse_ed2k_text(blob)
    assert len(links) == 1
    assert links[0].filename == "www.98T.la@初夏1.rar"
    assert links[0].size == 976158193
    assert links[0].hash == "B9DF3760FC34EEB3F7A14352325CF7C7"


def test_discuz_at_mention_url_inside_ed2k_filename():
    """tid=3304545：文件名里 @ 被渲成 [url=home.php…]@[/url]，勿误成 (1).mp4。"""
    blob = (
        "ed2k://|file|www.98T.la[url=home.php?mod=space&amp;uid=8039]@[/url] (1).mp4|"
        "225554687|3FC6682B071730668F198B022306D38F|/\n"
        "ed2k://|file|www.98T.la@ (2).mp4|193334576|2FCCA3575A074503F553F8387CFCA835|/"
    )
    links = parse_ed2k_text(blob)
    assert len(links) == 2
    assert links[0].filename == "www.98T.la@ (1).mp4"
    assert links[0].hash == "3FC6682B071730668F198B022306D38F"
    assert links[1].filename == "www.98T.la@ (2).mp4"
    assert links[1].hash == "2FCCA3575A074503F553F8387CFCA835"


def test_emoji_variant_names_merge():
    a = "⚠️リアルガチ童貞喪失⚠️【崩壊】童貞牧場001&002"
    b = "⚠リアルガチ童貞喪失⚠【崩壊】童貞牧場001&002"
    assert _names_emoji_equivalent(a, b)
    pa = ParsedAsset("ed2k", "A" * 32, a, 1, f"ed2k://|file|a|1|{'A'*32}|/")
    pb = ParsedAsset("ed2k", "B" * 32, b, 1, f"ed2k://|file|b|1|{'B'*32}|/")
    merged = _merge_truncated_name_groups([(a, pa, [pa]), (b, pb, [pb])])
    assert len(merged) == 1
    assert len(merged[0][2]) == 2
