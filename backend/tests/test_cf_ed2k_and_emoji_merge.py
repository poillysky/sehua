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


def test_emoji_variant_names_merge():
    a = "⚠️リアルガチ童貞喪失⚠️【崩壊】童貞牧場001&002"
    b = "⚠リアルガチ童貞喪失⚠【崩壊】童貞牧場001&002"
    assert _names_emoji_equivalent(a, b)
    pa = ParsedAsset("ed2k", "A" * 32, a, 1, f"ed2k://|file|a|1|{'A'*32}|/")
    pb = ParsedAsset("ed2k", "B" * 32, b, 1, f"ed2k://|file|b|1|{'B'*32}|/")
    merged = _merge_truncated_name_groups([(a, pa, [pa]), (b, pb, [pb])])
    assert len(merged) == 1
    assert len(merged[0][2]) == 2
