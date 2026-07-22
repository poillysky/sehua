"""无阅读权限：伪标题时用列表标题占位。"""

from workers.thread_outcome import judge_thread_html


def test_access_denied_uses_list_title_for_stub():
    html = """
    <html><head><title>提示信息</title></head>
    <body>抱歉，本帖要求阅读权限高于 10 才能浏览
    <div id="postmessage_1">请登录</div>
    Powered by Discuz!</body></html>
    """
    list_title = "【自整理】【115ed2k】君塚ひなた原档合集【15V/100GB】"
    out = judge_thread_html(
        html,
        board_fid="36",
        list_title=list_title,
        preferred_link="ed2k",
    )
    assert out.verdict == "stub"
    assert out.outcome == "无阅读权限 · 占位入库"
    assert out.title == list_title


def test_access_denied_skips_without_any_title():
    html = """
    <html><head><title>提示信息</title></head>
    <body>本帖要求阅读权限高于 10 才能浏览
    Powered by Discuz!</body></html>
    """
    out = judge_thread_html(
        html,
        board_fid="36",
        list_title="",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert "无有效标题" in out.outcome


def test_moderator_blocked_skips():
    html = """
    <html><head><title>【整理】【115ED2K】合集 - 论坛</title></head>
    <body>
      <span id="thread_subject">【整理】【115ED2K】合集</span>
      <div class="locked">提示: <em>该帖被管理员或版主屏蔽</em></div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【整理】【115ED2K】合集",
        preferred_link="ed2k",
    )
    assert out.verdict == "skipped"
    assert out.outcome == "版主屏蔽（跳过）"
    assert out.need_attachments is False


def test_author_banned_content_masked_skips():
    html = """
    <html><head><title>【BT种子】示例资源 - 论坛</title></head>
    <body>
      <span id="thread_subject">【BT种子】示例资源</span>
      <div class="locked">提示: <em>作者被禁止或删除 内容自动屏蔽</em></div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="95:716",
        list_title="【BT种子】示例资源",
        preferred_link="magnet",
    )
    assert out.verdict == "skipped"
    assert out.outcome == "作者已禁止（跳过）"
    assert out.need_attachments is False


def test_author_banned_not_triggered_when_post_has_body():
    """锁定提示残留但一楼已有正常正文 → 不当作作者已禁。"""
    html = """
    <html><head><title>【BT】有正文的帖 - 论坛</title></head>
    <body>
      <span id="thread_subject">【BT】有正文的帖</span>
      <div id="postmessage_1">
        这是正常可抓的资源说明文字，长度足够证明正文有效。
        ed2k://|file|demo.mp4|123|ABCDEF0123456789ABCDEF0123456789|/
      </div>
      <div class="locked">提示: <em>作者被禁止或删除 内容自动屏蔽</em></div>
      Powered by Discuz!
    </body></html>
    """
    html = html + ("<!-- pad -->" * 900)
    out = judge_thread_html(
        html,
        board_fid="2",
        list_title="【BT】有正文的帖",
        preferred_link="ed2k",
    )
    assert out.outcome != "作者已禁止（跳过）"
    assert out.verdict in {"import", "stub", "skipped"}


def test_locked_auto_mask_alone_not_author_banned():
    from parsers.thread_gates import is_thread_author_banned

    html = '<div class="locked">提示: <em>内容自动屏蔽</em></div>' + ("x" * 100)
    assert is_thread_author_banned(html) is False
