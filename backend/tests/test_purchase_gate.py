"""购买门：0 元可尝试解锁入库；付费跳过。"""

from parsers.thread_gates import (
    extract_purchase_buy_url,
    extract_purchase_price,
    is_free_purchase_post,
    is_purchase_required_post,
    purchase_gate_kind,
)
from workers.thread_outcome import judge_thread_html


_PAD = "<!-- " + ("x" * 200) + " -->\n"
_FREE_PW = (
    "<html><head><title>pacopacomama-060325_100 | 亞洲無碼 - 人人为我论坛</title></head><body>\n"
    + (_PAD * 50)
    + """
<div id="read_tpc" class="tpc_content">
<p>本内容需向作者支付   0金币</p>
<p><a href="job.php?action=buytopic&tid=27435887&pid=tpc&verify=abc&page=1">立即购买</a></p>
<p>购买人名单 -----------</p>
</div>
</body></html>
"""
)

# 2048 实页：售价在 #read_tpc 外的 .sell_content，且 0金币 被标签拆开
_FREE_PW_SELL_OUTSIDE = (
    "<html><head><title>【自转】【ED2K】demo | 亞洲無碼</title></head><body>\n"
    + (_PAD * 50)
    + """
<div id="read_tpc" class="tpc_content">
<p>【资源名称】：demo</p>
<p>【资源类型】：视频</p>
</div>
<div class="sell_content">本内容需向作者支付 <div class="coin"><span class="label label-warning">0金币</span></div>
<div class="pay_button"><a href="job.php?action=buytopic&tid=27425208&pid=tpc&verify=abc&page=1&token=" class="pay_button_a">立即购买</a></div>
</div>
</body></html>
"""
)

_PAID_PW = (
    "<html><head><title>付费资源 | 亞洲無碼 - 人人为我论坛</title></head><body>\n"
    + (_PAD * 50)
    + """
<div id="read_tpc" class="tpc_content">
<p>本内容需向作者支付   30金币</p>
<p><a href="job.php?action=buytopic&tid=1&pid=tpc">立即购买</a></p>
</div>
</body></html>
"""
)

_PAID_DZ = (
    "<html><head><title>付费主题 - 色花堂</title></head><body>\n"
    + (_PAD * 50)
    + """
<div id="postmessage_123" class="t_f">
本主题需向作者支付 15 金钱 才能浏览
</div>
</body></html>
"""
)


def test_extract_price_free_and_paid():
    assert extract_purchase_price(_FREE_PW) == 0
    assert extract_purchase_price(_PAID_PW) == 30
    assert extract_purchase_price(_PAID_DZ) == 15


def test_purchase_gate_kind():
    assert purchase_gate_kind(_FREE_PW) == "free"
    assert purchase_gate_kind(_PAID_PW) == "paid"
    assert purchase_gate_kind(_PAID_DZ) == "paid"
    assert purchase_gate_kind("<html>普通帖 magnet:?xt=urn:btih:A</html>") == "none"


def test_free_purchase_sell_content_outside_read_tpc():
    """sell_content 在楼主正文外时仍识别为 0 元购买。"""
    assert extract_purchase_price(_FREE_PW_SELL_OUTSIDE) == 0
    assert purchase_gate_kind(_FREE_PW_SELL_OUTSIDE) == "free"
    assert is_free_purchase_post(_FREE_PW_SELL_OUTSIDE) is True
    out = judge_thread_html(
        _FREE_PW_SELL_OUTSIDE, board_fid="36", forum_id="2048", preferred_link="magnet"
    )
    assert out.verdict == "stub"
    assert out.outcome == "0元购买贴"


def test_is_purchase_required_only_paid():
    assert is_free_purchase_post(_FREE_PW) is True
    assert is_purchase_required_post(_FREE_PW) is False
    assert is_purchase_required_post(_PAID_PW) is True


def test_extract_buy_url():
    url = extract_purchase_buy_url(_FREE_PW, "https://bbs.example.com/read.php?tid=1")
    assert "action=buytopic" in url
    assert url.startswith("https://bbs.example.com/")


def test_judge_paid_skips_not_stub():
    out = judge_thread_html(_PAID_PW, board_fid="4", forum_id="2048", preferred_link="magnet")
    assert out.verdict == "skipped"
    assert "付费" in out.outcome


def test_judge_free_stubs_for_account_crawl():
    out = judge_thread_html(_FREE_PW, board_fid="4", forum_id="2048", preferred_link="magnet")
    assert out.verdict == "stub"
    assert out.outcome == "0元购买贴"
    assert "付费" not in (out.outcome or "")


def test_unlock_free_purchase_refetch_on_success():
    import asyncio

    from workers.purchase_unlock import unlock_free_purchase_html

    locked = _FREE_PW
    unlocked = (
        "<html><head><title>ok</title></head><body>"
        + ("<!-- pad -->\n" * 80)
        + '<div id="read_tpc">magnet:?xt=urn:btih:'
        + ("A" * 40)
        + "&dn=demo</div></body></html>"
    )

    class _F:
        def set_referer(self, _u: str) -> None:
            return None

        async def get_html(self, url: str, mode: str = "http", retries: int = 2) -> str:
            assert "buytopic" in url
            return "<html>购买成功</html>"

        async def get_thread_html(self, url: str, retries: int = 2) -> str:
            return unlocked

    async def _run() -> None:
        html, note = await unlock_free_purchase_html(
            _F(), locked, "https://bbs.example.com/read.php?tid=1"
        )
        assert note == ""
        assert "magnet:" in html

    asyncio.run(_run())


def test_unlock_free_purchase_login_required():
    import asyncio

    from workers.purchase_unlock import unlock_free_purchase_html

    class _F:
        def set_referer(self, _u: str) -> None:
            return None

        async def get_html(self, url: str, mode: str = "http", retries: int = 2) -> str:
            return "<html><body>请先登录后继续操作</body></html>"

        async def get_thread_html(self, url: str, retries: int = 2) -> str:
            raise AssertionError("should not refetch")

    async def _run() -> None:
        html, note = await unlock_free_purchase_html(
            _F(), _FREE_PW, "https://bbs.example.com/read.php?tid=1"
        )
        assert html == _FREE_PW
        assert "需登录" in note

    asyncio.run(_run())


def test_unlock_skips_when_magnet_already_visible():
    """登录后售价文案仍在、但磁力已露出：不应报无购买链。"""
    import asyncio

    from workers.purchase_unlock import unlock_free_purchase_html

    already = (
        _FREE_PW.replace(
            "立即购买</a></p>",
            "立即购买</a></p><p>magnet:?xt=urn:btih:" + ("B" * 40) + "</p>",
        )
    )

    class _F:
        def set_referer(self, _u: str) -> None:
            raise AssertionError("should not buy")

        async def get_html(self, *a, **k):
            raise AssertionError("should not buy")

        async def get_thread_html(self, *a, **k):
            raise AssertionError("should not buy")

    async def _run() -> None:
        html, note = await unlock_free_purchase_html(
            _F(), already, "https://bbs.example.com/read.php?tid=1"
        )
        assert note == ""
        assert "magnet:" in html

    asyncio.run(_run())
