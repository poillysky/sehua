"""楼主二楼补链识别。"""

from __future__ import annotations

from parsers.content import extract_lz_posts_html
from parsers.links import parse_thread_dual
from workers.thread_outcome import judge_thread_html


def test_extract_lz_includes_second_floor():
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
    assert "115.com/s/sw6tpwf3n6m" in posts[1]
    assert "spam.mp4" not in "".join(posts)


def test_judge_imports_115_on_lz_second_floor():
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
    assert parsed.extract_password == "s192"

    out = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【ed2k链接】小女巫露娜",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.link_kind == "115share"
    assert out.parsed is not None
    assert out.parsed.share115_links
    assert out.parsed.share115_links[0].share_id == "sw6tpwf3n6m"
