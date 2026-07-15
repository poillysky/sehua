#!/usr/bin/env python3
"""Smoke-test dual magnet + ed2k parsing without network/DB."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.links import parse_thread_dual

SAMPLE = """
<html><body>
<span id="thread_subject">测试双解析资源</span>
<div class="t_f">
【影片名称】：Demo Movie<br>
【解压密码】：demo123<br>
magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01&amp;dn=Demo.Movie&amp;xl=1000
<br>
ed2k://|file|demo.zip|2048|AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA|/
</div>
<div class="blockcode">magnet:?xt=urn:btih:BBBBBB0123456789ABCDEF0123456789ABCDEF02&dn=Other</div>
</body></html>
"""


def main() -> int:
    result = parse_thread_dual(SAMPLE, tid=1, preferred_link="both")
    print("title:", result.title)
    print("primary:", result.primary_link_kind)
    print("magnets:", len(result.magnets), [m.infohash[:8] for m in result.magnets])
    print("ed2k:", len(result.ed2k_links), [e.hash[:8] for e in result.ed2k_links])
    print("primary assets:", [(a.link_kind, a.hash[:8]) for a in result.assets if a.is_primary])
    print("password:", result.extract_password)
    print("meta:", result.metadata)
    assert result.magnets and result.ed2k_links
    assert result.primary_link_kind == "magnet"
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
