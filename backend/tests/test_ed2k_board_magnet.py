"""ed2k 板块应接受磁力链接。"""

from __future__ import annotations

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


def test_cloud_share_not_when_magnet_present():
    text = f"网盘 https://pan.baidu.com/s/xxx\n{MAGNET}"
    assert not is_non_target_cloud_share(link_kind="ed2k", text=text)


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
