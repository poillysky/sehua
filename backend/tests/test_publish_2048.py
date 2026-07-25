# -*- coding: utf-8 -*-
from pathlib import Path

from crawler.publish_2048 import (
    expand_2048_entry_urls,
    is_2048_publish_url,
    parse_2048_publish_forum_links,
)

FIX = Path(__file__).resolve().parent.parent / "_tmp_fby.html"
SAMPLE = """
<section class="section">
  <h2>论坛今日地址</h2>
  <a class="link" href="/lt1.php">今日论坛新域</a>
  <a class="link" href="https://bbs.example-fast.com">论坛临时高速线路</a>
  <a class="link" href="https://bbs.mobile.example">移动用户专属通道</a>
</section>
<section class="section">
  <h2>影院今日地址</h2>
  <a class="link" href="https://yy.should-skip.com">今日影院新域</a>
</section>
<section class="section">
  <h2>免翻域名</h2>
  <a class="link" href="/bbs.php">地址 1 备用入口 免翻</a>
</section>
<section class="section">
  <h2>其他娱乐</h2>
  <a class="link" href="https://live.should-skip.com">聚合直播盒子</a>
</section>
"""


def test_is_2048_publish_url():
    assert is_2048_publish_url("https://fby.tfzqs88.com") is True
    assert is_2048_publish_url("https://fby.tfzqs88.com/") is True
    assert is_2048_publish_url("https://bbs.xfca2022.com/") is False
    assert is_2048_publish_url("https://ut2gw5.xc6ym5.com/") is False


def test_parse_publish_forum_links_skips_cinema():
    links = parse_2048_publish_forum_links(SAMPLE, "https://fby.tfzqs88.com/")
    assert "https://fby.tfzqs88.com/lt1.php" in links
    assert "https://bbs.example-fast.com" in links
    assert "https://bbs.mobile.example" in links
    assert "https://fby.tfzqs88.com/bbs.php" in links
    assert all("yy.should-skip" not in u for u in links)
    assert all("live.should-skip" not in u for u in links)


def test_parse_live_fby_fixture_if_present():
    if not FIX.is_file():
        return
    html = FIX.read_text(encoding="utf-8")
    links = parse_2048_publish_forum_links(html, "https://fby.tfzqs88.com/")
    assert links
    assert any("bbs." in u or u.endswith(".php") or ":5680" in u for u in links)
    assert all("yy.altongxue" not in u for u in links)
    assert all("nbjingjing" not in u for u in links)


def test_expand_keeps_direct_bbs():
    out = expand_2048_entry_urls(
        ["https://bbs.already.com/"],
        resolve_jumps=False,
        fetch_html=lambda _u: SAMPLE,
    )
    assert out == ["https://bbs.already.com/"]


def test_expand_publish_without_resolve():
    out = expand_2048_entry_urls(
        ["https://fby.tfzqs88.com/"],
        resolve_jumps=False,
        fetch_html=lambda _u: SAMPLE,
    )
    assert "https://bbs.example-fast.com/" in out or "https://bbs.example-fast.com" in [
        u.rstrip("/") for u in out
    ]
    assert any(u.rstrip("/").endswith("/lt1.php") or "lt1.php" in u for u in out)
    assert all("yy.should-skip" not in u for u in out)


def test_expand_only_first_publish_page():
    calls: list[str] = []

    def fetch(u: str) -> str:
        calls.append(u)
        return SAMPLE

    out = expand_2048_entry_urls(
        [
            "https://fby.tfzqs88.com/",
            "https://fby.js-bovey.com/",
            "https://bbs.direct.example/",
        ],
        resolve_jumps=False,
        fetch_html=fetch,
        max_publish_pages=1,
        max_entries=8,
    )
    assert len(calls) == 1
    assert calls[0].startswith("https://fby.tfzqs88.com")
    assert any("bbs.example-fast" in u for u in out)
    # bbs. 直链应排在发布页跳转脚本前面
    assert out[0].rstrip("/").startswith("https://bbs.")
    assert any("bbs.direct.example" in u for u in out) or len(out) >= 3


def test_expand_live_first_publish_fast():
    import time

    t0 = time.time()
    out = expand_2048_entry_urls(
        ["https://fby.tfzqs88.com/", "https://fby.js-bovey.com/"],
        resolve_jumps=False,
        max_publish_pages=1,
        max_entries=8,
        timeout=8.0,
    )
    elapsed = time.time() - t0
    assert elapsed < 15.0, f"expand too slow: {elapsed:.1f}s"
    assert out
    assert len(out) <= 8


def test_prioritize_preferred_entry_puts_last_good_first():
    from workers.session_factory import prioritize_preferred_entry

    entries = [
        "https://bbs.lurj7988.com/",
        "https://bbs.sbnlfe.cn/",
        "https://bbs.other.example/",
    ]
    out = prioritize_preferred_entry(entries, "https://bbs.sbnlfe.cn")
    assert out[0].rstrip("/").lower() == "https://bbs.sbnlfe.cn"
    assert len(out) == 3
    # 不在列表里的 preferred 仍插到最前
    out2 = prioritize_preferred_entry(entries, "https://bbs.remembered.example/")
    assert out2[0].startswith("https://bbs.remembered.example")
    assert len(out2) == 4
