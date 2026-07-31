"""抽链楼层：单资源看楼主多楼；多资源只看一楼；路人回帖默认排除。"""

from __future__ import annotations

from parsers.content import (
    extract_link_corpus_html,
    extract_lz_posts_html,
    should_scan_lz_multi_floor,
)
from parsers.links import parse_thread_dual
from workers.thread_outcome import judge_thread_html


def test_extract_lz_includes_lz_replies_ignores_guests():
    html = """
    <html><body>
    <div id="post_1">
      <div class="authi"><img class="authicn vm" src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <td id="postmessage_111">封面图 only</td>
    </div>
    <div id="post_2">
      <div class="authi"><img class="authicn vm" src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <td id="postmessage_222">
        115网盘: https://115.com/s/sw6tpwf3n6m 访问码:s192
      </td>
    </div>
    <div id="post_3">
      <div class="authi">路人甲</div>
      <td id="postmessage_333">ed2k://|file|spam.mp4|1|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/</td>
    </div>
    </body></html>
    """
    posts = extract_lz_posts_html(html, limit=5)
    assert len(posts) == 2
    assert "封面图" in posts[0]
    assert "115.com" in posts[1]
    assert all("spam.mp4" not in p for p in posts)
    corpus = extract_link_corpus_html(html)
    assert "封面图" in corpus
    assert "115.com" in corpus
    assert "spam.mp4" not in corpus


def test_second_floor_lz_link_imported():
    """楼主二楼补链应入库；路人回帖仍忽略。"""
    html = """
    <html><head><title>【ed2k链接】小女巫露娜 - 论坛</title></head>
    <body>
    <span id="thread_subject">【ed2k链接】小女巫露娜</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_111">只有封面</div>
    </div>
    <div id="post_2">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_222">
        【资源链接】: 115网盘: https://115.com/s/sw6tpwf3n6m 访问码:s192
        密码:TUTo9GeJxtG58J8FRaHR2CAj
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    parsed = parse_thread_dual(html, preferred_link="ed2k")
    assert parsed.primary_link_kind == "115share"
    assert parsed.share115_links

    out = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【ed2k链接】小女巫露娜",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.link_kind == "115share"


def test_main_post_magnet_keeps_reply_out():
    h1 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    h2 = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    html = f"""
    <html><body>
    <span id="thread_subject">合集</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />楼主</div>
      <div id="postmessage_1">
        【影片名称】：主贴片
        magnet:?xt=urn:btih:{h1}&dn=main
      </div>
    </div>
    <div id="post_2">
      <div class="authi">路人</div>
      <div id="postmessage_2">
        【影片名称】：回帖片
        magnet:?xt=urn:btih:{h2}&dn=reply
      </div>
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, preferred_link="magnet")
    hashes = {a.hash for a in parsed.assets if a.link_kind == "magnet"}
    assert h1 in hashes
    assert h2 not in hashes


def test_title_claims_ed2k_allows_reply_supplement():
    """tid=3300074：标题宣称 115eD2k，楼主只贴夸克，回帖补 ed2k 应入库。"""
    ed2k = "ed2k://|file|0207zhengyi.7z|4857700065|C7484664B24FAE1A684FABEEB6088E6B|/"
    html = f"""
    <html><body>
    <span id="thread_subject">【自转】【夸克/115eD2k】正义君合集【3V/4.53G/2配额】</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_111">
        【资源链接】夸克 https://pan.quark.cn/s/e766a75f4c25?pwd=NxVB
      </div>
    </div>
    <div id="post_2">
      <div class="authi">热心路人</div>
      <div id="postmessage_222">
        <div class="blockcode"><ol><li>{ed2k}</ol></div>
      </div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    corpus = extract_link_corpus_html(html)
    assert "0207zhengyi.7z" in corpus
    parsed = parse_thread_dual(html, preferred_link="magnet", tid=3300074)
    assert any(a.hash.upper() == "C7484664B24FAE1A684FABEEB6088E6B" for a in parsed.assets)
    out = judge_thread_html(
        html,
        board_fid="95",
        forum_id="sehuatang",
        list_title="【自转】【夸克/115eD2k】正义君合集【3V/4.53G/2配额】",
        preferred_link="magnet",
        tid=3300074,
    )
    assert out.verdict == "import"


def test_tid2625357_style_lz_second_floor_magnet():
    """一楼只有简介、楼主二楼贴磁力（tid 2625357 形态）。"""
    h = "44AE2C54CBECE13E275312DA35964B5C866194DB"
    html = f"""
    <html><head><title>演示帖 - 论坛</title></head>
    <body>
    <span id="thread_subject">演示帖</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_111">
        【影片名称】：演示片
        【影片大小】：2320MB
      </div>
    </div>
    <div id="post_2">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_222">
        磁力:&nbsp;&nbsp;magnet:?xt=urn:btih:{h}&amp;x._t-v1=555135672256563449
      </div>
    </div>
    <div id="post_3">
      <div class="authi">路人</div>
      <div id="postmessage_333">magnet:?xt=urn:btih:CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC&dn=spam</div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    parsed = parse_thread_dual(html, preferred_link="magnet")
    hashes = {a.hash for a in parsed.assets if a.link_kind == "magnet"}
    assert h in hashes
    assert "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC" not in hashes

    out = judge_thread_html(
        html,
        board_fid="103",
        list_title="演示帖",
        preferred_link="magnet",
    )
    assert out.verdict == "import"
    assert out.link_kind == "magnet"


def test_multi_resource_skips_lz_second_floor_links():
    """多资源（一楼≥2 名称标签）：不扫楼主二楼补链。"""
    h1 = "1111111111111111111111111111111111111111"
    h2 = "2222222222222222222222222222222222222222"
    h3 = "3333333333333333333333333333333333333333"
    html = f"""
    <html><body>
    <span id="thread_subject">合集两部</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_1">
        【影片名称】：甲片
        magnet:?xt=urn:btih:{h1}
        【影片名称】：乙片
        magnet:?xt=urn:btih:{h2}
      </div>
    </div>
    <div id="post_2">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_2">
        二楼补链 magnet:?xt=urn:btih:{h3}&dn=extra
      </div>
    </div>
    </body></html>
    """
    assert should_scan_lz_multi_floor(html) is False
    corpus = extract_link_corpus_html(html)
    assert h1.lower() in corpus.lower() or h1 in corpus
    assert h3 not in corpus
    parsed = parse_thread_dual(html, preferred_link="magnet")
    hashes = {a.hash.upper() for a in parsed.assets if a.link_kind == "magnet"}
    assert hashes == {h1, h2}
    assert h3 not in hashes


def test_single_resource_still_reads_lz_second_floor():
    """单资源（一楼仅 1 个名称）：仍看楼主二楼。"""
    h = "4444444444444444444444444444444444444444"
    html = f"""
    <html><body>
    <span id="thread_subject">单资源</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_1">
        【影片名称】：只有简介
        【影片大小】：1G
      </div>
    </div>
    <div id="post_2">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <div id="postmessage_2">
        magnet:?xt=urn:btih:{h}
      </div>
    </div>
    </body></html>
    """
    assert should_scan_lz_multi_floor(html) is True
    parsed = parse_thread_dual(html, preferred_link="magnet")
    assert any(a.hash.upper() == h for a in parsed.assets)


def test_op_not_truncated_by_nested_resource_table_tbody():
    """结构卡套表 </tbody> 不得截断一楼；表后 blockcode 链须入库（tid=3229469）。"""
    from parsers.content import extract_first_postmessage_html

    ed2k = (
        "ed2k://|file|www.98T.la@盗墓笔记作者周建龙.zip|14844966498|"
        "44B20280556FB7EC0180099520BA04BA|/"
    )
    html = f"""
    <html><body>
    <span id="thread_subject">【整理】【ED2K】盗墓笔记</span>
    <div id="post_1">
      <div class="authi"><img src="static/image/common/ico_lz.png" />&nbsp;楼主</div>
      <td id="postmessage_58189186">
        <table class="t_table"><tbody>
          <tr><td>【资源名称】：盗墓笔记音频合集</td></tr>
          <tr><td>【资源链接】：<br><br></td></tr>
        </tbody></table></td></tr></tbody></table><br>
        <div class="blockcode"><div id="code_jqA"><ol><li>{ed2k}</li></ol></div>
        <em>复制代码</em></div>
      </td>
    </div>
    <div id="post_2">
      <div class="authi">路人</div>
      <td id="postmessage_999">ed2k://|file|spam.zip|1|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/</td>
    </div>
    </body></html>
    """
    op = extract_first_postmessage_html(html)
    assert "blockcode" in op
    assert "盗墓笔记作者周建龙" in op
    parsed = parse_thread_dual(html, tid=3229469, preferred_link="ed2k")
    assert parsed.primary_link_kind == "ed2k"
    assert any(
        (a.hash or "").upper() == "44B20280556FB7EC0180099520BA04BA"
        for a in parsed.assets
    )
    assert any(
        "盗墓笔记作者周建龙" in (e.filename or "") for e in parsed.ed2k_links
    )
    outcome = judge_thread_html(
        html, board_fid=95, preferred_link="ed2k", forum_id="sehuatang", tid=3229469
    )
    assert outcome.verdict == "import"
    assert "成功" in (outcome.outcome or "")
