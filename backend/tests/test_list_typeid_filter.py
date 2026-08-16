"""汇总列表行 typeid 解析 + 父板入队过滤（排除版务等）。"""

from __future__ import annotations

from crawler.parser import ThreadBrief, parse_forum_list
from parsers.boards import (
    allowed_typeids_for_list_scan,
    list_row_enqueue_target,
)
from workers import list_scan as ls


LIST_HTML = """
<table>
<tbody id="normalthread_1001">
<th class="common">
<em>[<a href="forum.php?mod=forumdisplay&amp;fid=141&amp;filter=typeid&amp;typeid=689">国产合集</a>]</em>
<a href="thread-1001-1-1.html" class="s xst">资源A</a>
</th>
<td class="by"><em>2026-01-01</em></td>
</tbody>
<tbody id="normalthread_1002">
<th class="common">
<em>[<a href="forum.php?mod=forumdisplay&amp;fid=141&amp;filter=typeid&amp;typeid=708">版务</a>]</em>
<a href="thread-1002-1-1.html" class="s xst">版规说明</a>
</th>
<td class="by"><em>2026-01-01</em></td>
</tbody>
<tbody id="normalthread_1003">
<th class="common">
<em>[<a href="forum.php?mod=forumdisplay&amp;fid=141&amp;filter=typeid&amp;typeid=696">其它</a>]</em>
<a href="thread-1003-1-1.html" class="s xst">资源B</a>
</th>
<td class="by"><em>2026-01-01</em></td>
</tbody>
</table>
"""


def test_parse_forum_list_extracts_typeid():
    rows = parse_forum_list(LIST_HTML, skip_sticky=True)
    by_tid = {r.tid: r for r in rows}
    assert by_tid[1001].typeid == "689"
    assert by_tid[1002].typeid == "708"
    assert by_tid[1003].typeid == "696"


def test_allowed_typeids_parent_scan_excludes_banwu():
    enabled = ["141:689", "141:696", "95:716"]
    allow = allowed_typeids_for_list_scan("141", enabled)
    assert allow == frozenset({"689", "696"})
    assert allowed_typeids_for_list_scan("141:689", enabled) is None
    assert allowed_typeids_for_list_scan("95:716", enabled) is None


def test_list_row_enqueue_skips_banwu_and_disabled():
    allow = frozenset({"689", "696"})
    ok = list_row_enqueue_target("141", "689", allow_typeids=allow)
    assert ok is not None and ok[0] == "141:689"
    assert list_row_enqueue_target("141", "708", allow_typeids=allow) is None
    assert list_row_enqueue_target("141", "690", allow_typeids=allow) is None
    # 无 typeid 标记：保留，避免漏帖
    keep = list_row_enqueue_target("141", None, allow_typeids=allow)
    assert keep is not None and keep[0] == "141"


def test_enqueue_batch_filters_banwu(monkeypatch):
    out = ls.ListScanResult(board_fid=141)
    seen: set[int] = set()
    batch = [
        ThreadBrief(tid=1, title="A", url="u1", typeid="689"),
        ThreadBrief(tid=2, title="banwu", url="u2", typeid="708"),
        ThreadBrief(tid=3, title="B", url="u3", typeid="696"),
    ]
    inserted: list[str] = []

    def fake_enqueue(conn, **kwargs):
        inserted.append(str(kwargs.get("board_fid")))
        return True

    monkeypatch.setattr(ls, "connect", lambda: type("C", (), {"close": lambda self: None, "commit": lambda self: None, "rollback": lambda self: None})())
    monkeypatch.setattr(ls, "connect_resource", lambda: type("C", (), {"close": lambda self: None})())
    monkeypatch.setattr(ls, "known_resource_tids", lambda *_a, **_k: set())
    monkeypatch.setattr(ls, "enqueue_thread", fake_enqueue)
    monkeypatch.setattr(ls, "update_board_meta_by_tids", lambda *_a, **_k: 0)
    monkeypatch.setattr(ls, "update_crawl_board_meta_by_tids", lambda *_a, **_k: None)

    enq, young = ls._enqueue_batch(
        out,
        batch,
        seen=seen,
        board_fid="141",
        board_name="网友原创区",
        persist_enqueue=True,
        allow_typeids=frozenset({"689", "696"}),
    )
    assert enq == 2
    assert young == 0
    assert out.skipped_typeid == 1
    assert inserted == ["141:689", "141:696"]
