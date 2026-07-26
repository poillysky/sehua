"""PHPWind #read_tpc must win over truncated Discuz postmessage (comment_ cut)."""

from parsers.content import extract_link_corpus_html, extract_lz_scope_html
from parsers.links import parse_thread_dual
from parsers.thread_gates import extract_purchase_price, purchase_gate_kind
from workers.thread_outcome import judge_thread_html


_PAD = "<!-- " + ("x" * 200) + " -->\n"

# 混合模板：postmessage 在 comment_ 处被截断；售价+ed2k 仍在 #read_tpc 内
_HYBRID_PW = (
    "<html><head><title>【ED2K】demo | 磁链迅雷</title></head><body>\n"
    + (_PAD * 40)
    + """
<div id="read_tpc" class="tpc_content">
<div class="pcb"><div class="t_fsz"><table><tr>
<td class="t_f" id="postmessage_68141229">
<br>【资源名称】：LemonGarden 娜美<br>
【下载方式】：ED2K<br>
</td></tr></table></div>
<div id="comment_68141229" class="cm"></div>
此帖售价 0 金币,已有 10 人购买
<blockquote class="blockquote">
<ol><li>ed2k://|file|www.98T.la@demo.mp4|362237486|E1C2653B796DF3406DAC0155669983E8|/</li></ol>
</blockquote>
</div>
</div>
</body></html>
"""
)

_ATTACH_DENIED = (
    "<html><head><title>【115ED2K】写真合集</title></head><body>\n"
    + (_PAD * 40)
    + """
<div id="read_tpc" class="tpc_content">
【资源名称】：写真合集
【资源预览】：
本帖子中包含更多资源
您所在的用户组无法下载或查看附件
</div>
</body></html>
"""
)


def test_phpwind_read_tpc_includes_ed2k_after_comment():
    corpus = extract_link_corpus_html(_HYBRID_PW)
    scope = extract_lz_scope_html(_HYBRID_PW)
    assert "ed2k://" in corpus.lower()
    assert "此帖售价" in scope
    assert purchase_gate_kind(_HYBRID_PW) == "free"
    assert extract_purchase_price(_HYBRID_PW) == 0
    dual = parse_thread_dual(_HYBRID_PW, tid=1, preferred_link="ed2k", board_fid="318")
    assert dual.primary_link_kind == "ed2k"
    assert dual.ed2k_links
    out = judge_thread_html(
        _HYBRID_PW, board_fid="318", forum_id="2048", preferred_link="magnet", tid=1
    )
    assert out.verdict == "import"


def test_attachment_group_denied_stubs():
    out = judge_thread_html(
        _ATTACH_DENIED, board_fid="318", forum_id="2048", preferred_link="magnet", tid=2
    )
    assert out.verdict == "stub"
    assert "无权限下载附件" in (out.outcome or "")
