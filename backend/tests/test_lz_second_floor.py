"""主贴一楼抽链；回帖（含楼主二楼）不纳入。"""

from __future__ import annotations

from parsers.content import extract_link_corpus_html, extract_lz_posts_html
from parsers.links import parse_thread_dual
from workers.thread_outcome import judge_thread_html


def test_extract_lz_main_post_only_ignores_replies():
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
    assert len(posts) == 1
    assert "封面图" in posts[0]
    assert "115.com" not in posts[0]
    assert "spam.mp4" not in posts[0]
    corpus = extract_link_corpus_html(html)
    assert "封面图" in corpus
    assert "115.com" not in corpus
    assert "spam.mp4" not in corpus


def test_second_floor_link_not_imported():
    """楼主二楼补链也不算：子资源/链接只认主贴。"""
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
    assert parsed.primary_link_kind != "115share"
    assert not parsed.share115_links

    out = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【ed2k链接】小女巫露娜",
        preferred_link="ed2k",
    )
    # 主贴无链 → 不应因二楼 115 而 import
    assert out.verdict != "import" or out.link_kind != "115share"


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
