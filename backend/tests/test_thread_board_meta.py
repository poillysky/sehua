"""帖页二级板块解析。"""

from parsers.thread_gates import (
    extract_board_fid,
    extract_thread_typeid,
    resolve_thread_board_meta,
)


def test_extract_board_fid():
    assert extract_board_fid('<a href="forum.php?mod=viewthread&fid=103&tid=1">x</a>') == 103
    assert extract_board_fid('<a href="/forum-36-1.html">x</a>') == 36
    assert extract_board_fid("") is None


def test_extract_thread_typeid_with_fid():
    html = 'href="forum.php?mod=forumdisplay&amp;fid=95&amp;filter=typeid&amp;typeid=716"'
    assert extract_thread_typeid(html, "95") == "716"


def test_extract_thread_typeid_known_whitelist():
    # 综合讨论区情色分享在白名单
    html = 'somepage typeid=716 and other junk'
    assert extract_thread_typeid(html, "95") == "716"


def test_resolve_thread_board_meta_upgrades_bare_fid():
    html = (
        'fid=95&amp;filter=typeid&amp;typeid=716 '
        'forum.php?mod=viewthread&fid=95&tid=1'
    )
    key, name = resolve_thread_board_meta(html, fallback_key="95", fallback_name="综合讨论区")
    assert key == "95:716"
    assert "情色分享" in name or "·" in name


def test_resolve_keeps_subunit_when_no_typeid():
    key, name = resolve_thread_board_meta(
        "<html>fid=95</html>",
        fallback_key="95:716",
        fallback_name="综合讨论区 · 情色分享",
    )
    assert key == "95:716"
    assert "情色分享" in name


def test_resolve_prefers_fallback_fid_over_sidebar():
    # 侧栏先出现 fid=95，正文/回退是国产原创 2:684
    html = (
        'fid=95&amp;filter=typeid&amp;typeid=716 '
        'forum.php?mod=viewthread&fid=2&tid=1333394 '
        'fid=2&amp;filter=typeid&amp;typeid=684'
    )
    key, name = resolve_thread_board_meta(
        html,
        fallback_key="2:684",
        fallback_name="国产原创 · 国产无码",
    )
    assert key == "2:684"
    assert "国产" in name


def test_resolve_never_returns_empty_name_for_fid2():
    key, name = resolve_thread_board_meta(
        "<html>fid=2</html>",
        fallback_key="2",
        fallback_name="",
    )
    assert key == "2"
    assert name == "国产原创"
    assert not name.lower().startswith("fid")


def test_extract_typeid_ignores_unrelated_filter():
    # filter=typeid=716 属于 95，不能套到 fid=2
    html = 'filter=typeid&amp;typeid=716 <a href="forum.php?fid=2">x</a>'
    assert extract_thread_typeid(html, "2") is None
