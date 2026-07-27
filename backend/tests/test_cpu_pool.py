"""cpu_pool / cpu_jobs smoke：重载荷识别与进程池调用。"""

from __future__ import annotations

import asyncio

from workers.cpu_jobs import job_parse_thread_dual
from workers.cpu_pool import is_heavy_parse_payload, run_parse_job


def test_is_heavy_parse_payload():
    from workers.cpu_pool import HEAVY_ATTACH_CHARS, HEAVY_TOTAL_CHARS

    assert not is_heavy_parse_payload("x" * 1000, "")
    # 普通 Discuz 帖页 ~90KB：不应再进进程池（避免占满唯一 worker）
    assert not is_heavy_parse_payload("z" * 90_000, "")
    assert not is_heavy_parse_payload("z" * 120_000, "")
    # 大附件语料
    assert is_heavy_parse_payload("", "y" * 30_000)
    assert is_heavy_parse_payload("h" * 10_000, "a" * HEAVY_ATTACH_CHARS)
    # 超大合计
    assert is_heavy_parse_payload("z" * HEAVY_TOTAL_CHARS, "")
    # 正文内嵌海量磁力
    magnets = "\n".join(
        f"magnet:?xt=urn:btih:{i:040x}" for i in range(100)
    )
    assert is_heavy_parse_payload(("pad" * 15_000) + magnets, "")


def test_job_parse_thread_dual_small():
    html = (
        "<html><head><title>demo</title></head><body>"
        "<div id='postmessage_1'>"
        "【影片名称】：ABF-261<br>"
        "【影片大小】：1.0GB<br>"
        "magnet:?xt=urn:btih:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "</div></body></html>"
    )
    # pad to avoid soft-shell heuristics if any
    html = html + ("<!-- pad -->" * 800)
    parsed = job_parse_thread_dual(
        {
            "html": html,
            "tid": 1,
            "preferred_link": "magnet",
            "extra_text": "",
            "base_url": "https://www.sehuatang.net/",
            "board_fid": "36",
        }
    )
    assert parsed.assets or parsed.magnets


def test_thread_tid_key_for_attach_reuse():
    from crawler.attachments import _thread_tid_key

    assert _thread_tid_key("https://x/forum.php?mod=viewthread&tid=3351756") == "3351756"
    assert _thread_tid_key("https://x/thread-3351756-1-1.html") == "3351756"
    assert _thread_tid_key("https://x/thread-1-1-1.html") != _thread_tid_key(
        "https://x/thread-2-1-1.html"
    )


def test_heavy_attachment_outcome_skips_rejudge():
    """大包附件：_outcome_from_heavy_attachment 一次 parse 即可 import。"""
    from workers.pipeline import _outcome_from_heavy_attachment
    from workers.thread_outcome import ThreadOutcome

    html = (
        "<html><head><title>大包</title></head><body>"
        "<span id='thread_subject'>合集大包</span>"
        "<div id='postmessage_1'>见附件</div>"
        "</body></html>"
    ) + ("<!-- pad -->" * 900)
    lines = [f"magnet:?xt=urn:btih:{i:040x}&dn=pack{i}" for i in range(60)]
    attach = "\n".join(lines) + ("\n#pad" * 4000)
    assert len(attach) >= 24_000

    prior = ThreadOutcome(
        "need_attachments",
        "正文无磁力，尝试 Excel/文本附件",
        "magnet",
        "合集大包",
        need_attachments=True,
        attachment_kind="txt_tail",
    )

    async def _run():
        return await _outcome_from_heavy_attachment(
            html,
            tid=3351756,
            list_title="合集大包",
            prior=prior,
            preferred_link="magnet",
            base_url="https://www.sehuatang.net/thread-3351756-1-1.html",
            board_fid="36",
            attachment_text=attach,
        )

    out = asyncio.run(_run())
    assert out.verdict == "import"
    assert out.parsed is not None
    assert len(out.parsed.assets) >= 1
    assert "附件" in (out.outcome or "")


def test_run_parse_job_light_uses_thread():
    html = "<html><body>magnet:?xt=urn:btih:" + ("A" * 40) + "</body></html>"
    html = html + ("<!-- p -->" * 900)

    async def _run():
        return await run_parse_job(
            job_parse_thread_dual,
            {
                "html": html,
                "tid": 2,
                "preferred_link": "magnet",
                "extra_text": "",
                "base_url": "https://www.sehuatang.net/",
                "board_fid": "36",
            },
            html=html,
            extra="",
        )

    parsed = asyncio.run(_run())
    assert parsed is not None
