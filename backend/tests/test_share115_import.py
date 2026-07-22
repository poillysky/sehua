"""115 分享码资源识别与入库。"""

from __future__ import annotations

from parsers.share115 import parse_115_share_text, share115_hash
from parsers.links import parse_thread_dual
from workers.thread_outcome import judge_thread_html


def test_parse_115_share_url_and_access_code():
    text = """
    【资源链接】：https://115cdn.com/s/swf6jpt3ngd?password=1122#
    115访问码：1122
    百度网盘提取码：wwpa
    """
    links = parse_115_share_text(text, title="测试游戏")
    assert len(links) == 1
    assert links[0].share_id == "swf6jpt3ngd"
    assert links[0].password == "1122"
    assert "115cdn.com/s/swf6jpt3ngd" in links[0].url
    assert "password=1122" in links[0].url
    assert links[0].hash == share115_hash("swf6jpt3ngd", "115cdn.com")


def test_parse_115_com_share_with_labeled_code():
    text = "链接 https://115.com/s/abc123XYZ\n访问码：a1b2"
    links = parse_115_share_text(text)
    assert len(links) == 1
    assert links[0].share_id == "abc123XYZ"
    assert links[0].password == "a1b2"


def test_judge_imports_115_share_as_primary():
    html = """
    <html><head><title>【整理】【115网盘分享】游戏【2G】 - 论坛</title></head>
    <body>
    <span id="thread_subject">【整理】【115网盘分享】游戏【2G】</span>
    <div id="postmessage_1">
      【资源链接】：<a href="https://115cdn.com/s/swf6jpt3ngd?password=1122#">https://115cdn.com/s/swf6jpt3ngd?password=1122#</a><br/>
      115访问码：1122<br/>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【整理】【115网盘分享】游戏【2G】",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.link_kind == "115share"
    assert "115" in out.outcome
    assert out.parsed is not None
    assert out.parsed.primary_link_kind == "115share"
    assert out.parsed.extract_password == "1122"
    assert out.parsed.assets
    assert out.parsed.assets[0].uri.startswith("https://115cdn.com/s/")


def test_ed2k_still_preferred_over_115_share():
    html = """
    <html><head><title>【115eD2k】合集 - 论坛</title></head>
    <body>
    <span id="thread_subject">【115eD2k】合集</span>
    <div id="postmessage_1">
      <div class="blockcode"><ol>
        <li>ed2k://|file|demo.mp4|10|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/
      </ol></div>
      另：https://115cdn.com/s/swf6jpt3ngd?password=1122
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid=95,
        list_title="【115eD2k】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "import"
    assert out.parsed is not None
    assert out.parsed.primary_link_kind == "ed2k"


def test_parse_thread_dual_115_sets_password():
    html = """
    <html><body>
    <span id="thread_subject">【115分享码】测试</span>
    <div id="postmessage_1">
      https://115cdn.com/s/swfsqpb3h7k?password=c233#
    </div>
    </body></html>
    """
    parsed = parse_thread_dual(html, preferred_link="ed2k")
    assert parsed.primary_link_kind == "115share"
    assert parsed.extract_password == "c233"
