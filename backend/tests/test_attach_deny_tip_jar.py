"""2048 打赏脚本「请先登录再打赏」不得误判为无权下载附件。"""

from __future__ import annotations

from parsers.attachments import (
    is_attachment_denied,
    is_attachment_download_limited,
    is_attachment_login_required,
    thread_body_shows_attach_denied,
)
from workers.thread_outcome import judge_thread_html

_PAD = "<!-- " + ("x" * 200) + " -->\n"


def _page(body: str, *, tip_jar: bool = True) -> str:
    tip = ""
    if tip_jar:
        tip = """
<script>
function tip(){
  alert('请先登录再打赏');
}
</script>
"""
    return (
        "<html><head><title>帖子 demo</title></head><body>\n"
        + (_PAD * 40)
        + tip
        + f'<div id="read_tpc" class="tpc_content">{body}</div>\n'
        + "</body></html>"
    )


def test_tip_jar_login_not_attachment_denied():
    html = _page("正文只有预览图，无附件无链")
    assert is_attachment_denied(html) is False
    assert thread_body_shows_attach_denied(html) is False


def test_baidu_pan_with_tip_jar_skips_not_attach_stub():
    """tid=27424394 类：标题百度网盘 + 打赏脚本 → 跳过网盘，不是无权附件。"""
    html = _page(
        "【百度网盘】里番<br>pan.baidu.com/s/1CYCD238lgktzZVMmJKJHVA?pwd=2333",
        tip_jar=True,
    )
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【百度网盘】【里番】demo",
        preferred_link="magnet",
        tid=27424394,
    )
    assert out.verdict == "skipped"
    assert "百度" in (out.outcome or "")
    assert "附件无权（占位入库）" not in (out.outcome or "")


def test_torrent_attach_with_tip_jar_tries_attachment():
    """BT 种子帖：全页有打赏脚本时仍应尝试下种子，勿提前 stub。"""
    html = _page(
        "【BT种子】demo<br>"
        "<div class='attach-card'>"
        "<a href='job.php?action=download&aid=1'>2048.cc-1.torrent</a>"
        "</div>",
        tip_jar=True,
    )
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【BT种子】demo",
        preferred_link="magnet",
        tid=27425247,
        base_url="https://bbs.example.com/",
    )
    assert out.verdict == "need_attachments"
    assert out.attachment_kind == "torrent"


def test_free_purchase_with_tip_jar_is_zero_yuan_stub():
    """0 元购买未解锁：应 0元购买贴，不是无权下载附件。"""
    html = _page(
        "【ED2K】demo<br>"
        '<div class="sell_content">此帖售价 0 金币,已有 3 人购买 立即购买</div>',
        tip_jar=True,
    )
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【ED2K丨自转】demo",
        preferred_link="magnet",
        tid=27425335,
    )
    assert out.verdict == "stub"
    assert out.outcome == "0元购买贴"


def test_real_group_denied_still_stubs():
    html = _page(
        "本帖子中包含更多资源<br>您所在的用户组无法下载或查看附件",
        tip_jar=True,
    )
    assert thread_body_shows_attach_denied(html) is True
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        preferred_link="magnet",
        tid=2,
    )
    assert out.verdict == "stub"
    assert "附件无权（占位入库）" in (out.outcome or "")


def test_discuz_specific_user_attach_tip_stubs():
    """tid=2365987：Discuz「只有特定用户可以下载本站附件」→ 占位，勿跳过。"""
    tip = (
        "<html><head><title>提示信息</title></head><body>"
        "<div>抱歉，只有特定用户可以下载本站附件</div>"
        "<form>用户登录</form></body></html>"
    )
    assert is_attachment_denied(tip) is True

    html = (
        "<html><body>"
        + (_PAD * 40)
        + '<div id="postmessage_1">'
        "【自转】demo<br>"
        '<ignore_js_op><a href="forum.php?mod=attachment&aid=1">资源.txt</a></ignore_js_op>'
        "</div></body></html>"
    )
    out = judge_thread_html(
        html,
        board_fid="95:716",
        forum_id="sehuatang",
        list_title="【自转】demo",
        preferred_link="ed2k",
        tid=2365987,
        base_url="https://www.sehuatang.net/",
        attachments_already_tried=True,
        attachment_denied=True,
    )
    assert out.verdict == "stub"
    assert out.outcome == "附件无权（占位入库）"


def test_attach_download_login_tip_stubs_as_attach_denied():
    """tid=27424341：附件直链落到「请先登录」提示页 → 占位「附件无权（占位入库）」，勿跳过。"""
    tip = """
<html><head><title>提示信息</title></head><body>
<div class="f14">登录提示</div>
您没有登录或者没有权限访问此页面，请先登录：
</body></html>
"""
    assert is_attachment_login_required(tip) is True
    assert is_attachment_denied(tip) is True

    html = _page(
        "【ED2K丨整理】demo<br>"
        "<div class='attach-card'>"
        "<a href='job.php?action=download&aid=1'>2048.cc-1.txt</a>"
        "</div>",
        tip_jar=True,
    )
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【ED2K丨整理】葵野まりんHEVC精选合集",
        preferred_link="magnet",
        tid=27424341,
        base_url="https://bbs.xfca2022.com/",
        attachments_already_tried=True,
        attachment_login_required=True,
    )
    assert out.verdict == "stub"
    assert out.outcome == "附件无权（占位入库）"

    # 有附件区已试仍无链（未带 denied 标志）也按无权占位，勿「未解析到…跳过」
    out2 = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【ED2K丨整理】葵野まりんHEVC精选合集",
        preferred_link="magnet",
        tid=27424341,
        base_url="https://bbs.xfca2022.com/",
        attachments_already_tried=True,
    )
    assert out2.verdict == "stub"
    assert out2.outcome == "附件无权（占位入库）"


def test_attach_daily_limit_tip_is_denied():
    """账号日限「今天下载 txt 已达 N 个」→ 无权占位，勿「附件下载失败」。"""
    tip = """
<html><head><title>提示信息</title></head><body>
""" + ("<!-- pad -->\n" * 400) + """
今天下载 txt 已达 <b style='color:red;'>50</b> 个，请明天再来。<br><br>
🚀 如需 完全无限制下载 👉 点此购买无限制账号
</body></html>
"""
    assert is_attachment_download_limited(tip) is True
    assert is_attachment_denied(tip) is True
    assert is_attachment_login_required(tip) is False

    html = _page(
        "【ED2K丨整理】demo<br>"
        "<div class='attach-card'>"
        "<a href='job.php?action=download&aid=1'>2048.cc-1.txt</a>"
        "</div>",
        tip_jar=True,
    )
    out = judge_thread_html(
        html,
        board_fid="318",
        forum_id="2048",
        list_title="【ED2K丨整理】demo",
        preferred_link="magnet",
        tid=27424341,
        base_url="https://bbs.xfca2022.com/",
        attachments_already_tried=True,
        attachment_denied=True,
    )
    assert out.verdict == "stub"
    assert out.outcome == "附件无权（占位入库）"


def test_login_tip_deep_in_html_still_detected():
    """提示文案在 9KB+ 处时仍应识别（勿只扫前 4KB）。"""
    tip = (
        "<html><head><title>提示信息</title></head><body>\n"
        + ("<!-- " + ("x" * 200) + " -->\n") * 50
        + "登录提示\n您没有登录或者没有权限访问此页面，请先登录：\n"
        + "</body></html>"
    )
    assert tip.find("您没有登录") > 4000
    assert is_attachment_login_required(tip) is True
    assert is_attachment_denied(tip) is True
