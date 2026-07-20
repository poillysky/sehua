"""对照线上文案：{用户名}，如果您要查看本帖隐藏内容请<a>回复</a> → 占位。"""

from parsers.thread_gates import is_reply_required_post, is_safe_or_soft_shell
from workers.thread_outcome import judge_thread_html

# 截图同款：登录用户名 + 中文逗号 + 请与「回复」链拆开
_DISCORD_REPLY_HTML = """
<html><head><title>资源帖 - sehuatang</title></head>
<body>
<div id="postmessage_12345" class="t_f">
  <div class="showhide" style="border:1px dashed #FF9A9A">
    <img src="static/image/common/lock.gif" alt=""/>
    poilly，如果您要查看本帖隐藏内容请
    <a href="forum.php?mod=post&amp;action=reply&amp;tid=3634959&amp;extra=page%3D1"
       onclick="showWindow('reply', this.href)">回复</a>
  </div>
</div>
<div>Powered by Discuz!</div>
</body></html>
"""


def test_screenshot_copy_logged_in_username():
    assert is_safe_or_soft_shell(_DISCORD_REPLY_HTML) is False
    assert is_reply_required_post(_DISCORD_REPLY_HTML) is True
    out = judge_thread_html(
        _DISCORD_REPLY_HTML,
        board_fid=36,
        list_title="某需回复资源帖",
    )
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"
    assert out.need_browser_retry is False
    assert out.need_attachments is False


def test_screenshot_copy_guest_prefix():
    html = _DISCORD_REPLY_HTML.replace("poilly，", "游客，")
    assert is_reply_required_post(html) is True
    out = judge_thread_html(html, board_fid=2, list_title="x")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"


def test_soft_shell_safeid_still_first():
    html = "<html><script>var safeid='abc';</script><title>名人名言</title><body>x</body></html>"
    assert is_safe_or_soft_shell(html) is True
    out = judge_thread_html(html, board_fid=36, list_title="x")
    assert out.verdict == "retry"
    assert out.need_browser_retry is True
