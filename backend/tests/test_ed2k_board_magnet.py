"""ed2k 板块应接受磁力链接。"""

from __future__ import annotations

from parsers.magnet import normalize_magnet_corpus, parse_magnet_text
from parsers.thread_gates import has_target_link, is_non_target_cloud_share
from workers.thread_outcome import judge_thread_html


MAGNET = (
    "magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01"
    "&dn=sample"
)


def test_has_target_link_ed2k_accepts_magnet():
    assert has_target_link(MAGNET, "ed2k")
    assert not has_target_link("https://pan.baidu.com/s/abc", "ed2k")
    assert has_target_link("ed2k://|file|a.mkv|1|ABCDEFABCDEFABCDEFABCDEFABCDEFAB|/", "ed2k")


def test_incomplete_ed2k_not_target_link():
    """缺 hash 的半截 ed2k / d2k 不应算有目标链（常见发帖截断）。"""
    broken = "ed2k://|file|www.98T.la@demo.zip|509285037|"
    broken_d2k = "d2k://|file|www.98T.la@demo.zip|509285037|"
    assert not has_target_link(broken, "ed2k")
    assert not has_target_link(broken_d2k, "ed2k")
    assert is_non_target_cloud_share(
        link_kind="ed2k",
        text=broken + "\nhttps://pan.baidu.com/s/1abcDEF?pwd=xxxx",
    )


def test_cloud_share_not_when_magnet_present():
    text = f"网盘 https://pan.baidu.com/s/xxx\n{MAGNET}"
    assert not is_non_target_cloud_share(link_kind="ed2k", text=text)


def test_parse_fullwidth_colon_magnet():
    """中文全角冒号 magnet：?xt=urn：btih：… 应能解析。"""
    raw = "magnet：?xt=urn：btih：33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    assert "magnet:?" in normalize_magnet_corpus(raw)
    links = parse_magnet_text(raw)
    assert len(links) == 1
    assert links[0].infohash == "33C4355AE4E69DB5AAA568E825A552ED29FD75BB"
    assert has_target_link(raw, "ed2k")
    assert has_target_link(raw, "magnet")


def test_parse_colonless_magnet_anti_filter():
    """附件防和谐去冒号：magnetxt=urnbtih:HASH 应还原。"""
    raw = (
        "magnetxt=urnbtih:2C01890375D5F1D3C91DA109F807EB680FD38D9D\n"
        "magnetxt=urnbtih:7B9851F0E832003BD5CE0B845D3D06D44CE49EA2"
    )
    fixed = normalize_magnet_corpus(raw)
    assert "magnet:?xt=urn:btih:2C01890375D5F1D3C91DA109F807EB680FD38D9D" in fixed
    links = parse_magnet_text(raw)
    assert len(links) == 2
    assert links[0].infohash == "2C01890375D5F1D3C91DA109F807EB680FD38D9D"
    assert has_target_link(raw, "ed2k")
    assert has_target_link(raw, "magnet")


def test_parse_truncated_ed2k_scheme():
    """发帖掐掉 e：d2k://|file|… 应还原为 ed2k。"""
    from parsers.ed2k import normalize_ed2k_corpus, parse_ed2k_text

    raw = (
        "d2k://|file|www.98T.la@demo.mp4|2130880573|5EDD1B7979E9B5B98377D0E4B66624EA|/"
    )
    assert normalize_ed2k_corpus(raw).startswith("ed2k://")
    links = parse_ed2k_text(raw)
    assert len(links) == 1
    assert links[0].hash == "5EDD1B7979E9B5B98377D0E4B66624EA"
    assert links[0].link.startswith("ed2k://")
    assert has_target_link(raw, "ed2k")


def test_judge_imports_truncated_ed2k_scheme():
    html = """
    <html><head><title>【自转】【eD2k链接】掐字母测试</title></head>
    <body>
    <span id="thread_subject">【自转】【eD2k链接】掐字母测试</span>
    <div id="postmessage_1">
      <div class="blockcode"><div id="code_x"><ol>
        <li>d2k://|file|www.98T.la@demo.mp4|2130880573|5EDD1B7979E9B5B98377D0E4B66624EA|/
      </ol></div></div>
    </div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    outcome = judge_thread_html(
        html,
        board_fid=95,
        list_title="【自转】【eD2k链接】掐字母测试",
        preferred_link="ed2k",
    )
    assert outcome.verdict == "import"
    assert outcome.parsed is not None
    assert outcome.parsed.ed2k_links
    assert outcome.parsed.ed2k_links[0].hash == "5EDD1B7979E9B5B98377D0E4B66624EA"


def test_judge_ed2k_board_imports_magnet_only():
    html = f"""
    <html><head><title>测试磁力资源贴</title></head>
    <body>
    <div id="postmessage_1">{MAGNET}</div>
    Powered by Discuz!
    </body></html>
    """
    # pad length so short-html / soft-shell gates do not fire
    html = html + ("<!-- pad -->" * 900)

    outcome = judge_thread_html(html, board_fid=95, list_title="测试磁力资源贴")
    assert outcome.verdict == "import"
    assert outcome.link_kind == "magnet"
    assert outcome.parsed is not None
    assert outcome.parsed.primary_link_kind == "magnet"
    assert outcome.parsed.assets


def test_judge_imports_fullwidth_colon_magnet():
    html = """
    <html><head><title>【磁力】全角冒号测试</title></head>
    <body>
    <span id="thread_subject">【磁力】全角冒号测试</span>
    <div id="postmessage_1">magnet：?xt=urn：btih：33C4355AE4E69DB5AAA568E825A552ED29FD75BB</div>
    Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    outcome = judge_thread_html(
        html,
        board_fid="141:690",
        list_title="【磁力】全角冒号测试",
        preferred_link="ed2k",
    )
    assert outcome.verdict == "import"
    assert outcome.parsed is not None
    assert outcome.parsed.magnets
