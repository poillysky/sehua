"""软文壳不得误伤真帖；需回复贴占位入库（非龄期板 / 已满龄）。"""

from parsers.thread_gates import is_reply_required_post, is_safe_or_soft_shell
from workers.thread_outcome import judge_thread_html


def test_soft_shell_safeid():
    html = "<html><script>var safeid='abc';</script><body>名人名言</body></html>"
    assert is_safe_or_soft_shell(html) is True


def test_soft_shell_short_without_discuz_footer_no_post():
    html = "<html><title>伍德罗·威尔逊</title><body>一句名言</body></html>"
    assert is_safe_or_soft_shell(html) is True


def test_real_thread_short_fragment_not_soft_shell():
    # 有一楼正文：即使短、无 Powered by，也不是软文
    html = """
    <div id="postmessage_1">
      游客，如果您要查看本帖隐藏内容请<a href="forum.php?mod=post&action=reply">回复</a>
    </div>
    """
    assert is_safe_or_soft_shell(html) is False
    assert is_reply_required_post(html) is True


def test_reply_gate_with_anchor_between_请_and_回复():
    html = """
    <div id="postmessage_1">
      <div class="showhide">
        游客，如果您要查看本帖隐藏内容请<a href="forum.php?mod=post&action=reply&tid=3634959">回复</a>
      </div>
      <div class="attach">附件: foo.torrent</div>
    </div>
    """
    assert is_safe_or_soft_shell(html) is False
    assert is_reply_required_post(html) is True
    out = judge_thread_html(html, board_fid=36, list_title="某资源帖")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"
    assert out.need_attachments is False
    assert out.need_browser_retry is False


def test_reply_gate_plain_space():
    html = "<div id='postmessage_1'>如果您要查看本帖隐藏内容请 回复 </div>"
    assert is_safe_or_soft_shell(html) is False
    out = judge_thread_html(html, board_fid=95, list_title="测试")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"


def test_reply_before_magnet_attachment_retry():
    html = """
    <html><body>
    <div id="postmessage_2">隐藏内容请<a href="#">回复</a>后可见</div>
    <div class="t_f">download.php?aid=1&amp;.torrent</div>
    </body></html>
    """
    out = judge_thread_html(html, board_fid=36, list_title="磁力暗示 magnet")
    assert out.verdict == "stub"
    assert out.outcome == "需回复贴"
    assert out.need_attachments is False


def test_soft_shell_still_first_when_no_post_body():
    html = "<html><title>请稍候</title><body>loading</body></html>"
    assert is_safe_or_soft_shell(html) is True
    out = judge_thread_html(html, board_fid=36, list_title="x")
    assert out.verdict == "retry"
    assert out.need_browser_retry is True
