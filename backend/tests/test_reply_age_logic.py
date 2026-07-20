"""需回复占位 vs 网友原创区未满龄跳过。"""

from datetime import datetime, timedelta

from parsers.list_dates import extract_thread_posted_at
from parsers.thread_gates import is_reply_required_post, is_safe_or_soft_shell
from workers.thread_outcome import judge_thread_html


def _reply_html(*, posted: str | None = None, username: str = "poilly") -> str:
    posted_line = f'<em id="authorposton1">发表于 {posted}</em>' if posted else ""
    return f"""
<html><head><title>资源帖 - sehuatang</title></head>
<body>
{posted_line}
<div id="postmessage_12345" class="t_f">
  <div class="showhide">
    {username}，如果您要查看本帖隐藏内容请
    <a href="forum.php?mod=post&amp;action=reply&amp;tid=3634959">回复</a>
  </div>
</div>
<div>Powered by Discuz!</div>
</body></html>
"""


def test_extract_thread_posted_at():
    html = '<em id="authorposton1">发表于 2026-7-18 12:30:00</em>'
    dt = extract_thread_posted_at(html)
    assert dt == datetime(2026, 7, 18, 12, 30, 0)


def test_reply_stub_when_old_enough_on_141():
    # 发帖已超过 3 天 → 需回复占位
    old = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    html = _reply_html(posted=old)
    assert is_safe_or_soft_shell(html) is False
    assert is_reply_required_post(html) is True
    out = judge_thread_html(html, board_fid="141:689", list_title="合集帖")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"


def test_reply_skip_when_young_on_141():
    # 未满 3 天 → 跳过，不占位
    young = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = _reply_html(posted=young)
    out = judge_thread_html(html, board_fid="141:866", list_title="新帖")
    assert out.verdict == "skipped"
    assert "未满" in out.outcome
    assert "3" in out.outcome


def test_reply_stub_on_non_age_board():
    # 非龄期板：即使很新也占位（无龄期策略）
    young = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = _reply_html(posted=young)
    out = judge_thread_html(html, board_fid="36:368", list_title="FC2")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"


def test_soft_shell_still_first():
    html = "<html><script>var safeid='x';</script><title>名人名言</title><body></body></html>"
    out = judge_thread_html(html, board_fid="141:689", list_title="x")
    assert out.verdict == "retry"
    assert out.need_browser_retry is True
