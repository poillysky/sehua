# -*- coding: utf-8 -*-
"""正文残链复判：附件失败/无权优先于「待核/漏链」。"""

from __future__ import annotations

from parsers.attachments import AttachmentFetchResult
from parsers.skip_outcomes import (
    RETRY_ATTACH_FAILED,
    SKIP_ATTACH_EMPTY,
    STUB_ATTACH_DENIED,
)
from workers.attach_trigger import outcome_from_attach_rejudge_failure


def test_rejudge_attach_failed_is_retry():
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(failed=True),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "retry"
    assert out.outcome == RETRY_ATTACH_FAILED


def test_rejudge_attach_denied_is_stub():
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(denied=True),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "stub"
    assert out.outcome == STUB_ATTACH_DENIED


def test_rejudge_denied_beats_junk_text():
    """无权提示页当 text 带回时仍占位，勿合并正文待核。"""
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(
            denied=True,
            text="抱歉，只有特定用户可以下载本站附件",
        ),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "stub"
    assert out.outcome == STUB_ATTACH_DENIED


def test_rejudge_attach_login_is_stub():
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(login_required=True),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "stub"
    assert out.outcome == STUB_ATTACH_DENIED


def test_rejudge_attach_empty_is_skip():
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(empty_attachment=True),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "skipped"
    assert out.outcome == SKIP_ATTACH_EMPTY


def test_rejudge_downloaded_but_no_text_is_retry():
    """下到空语料也算下载失败优先，勿回落正文待核。"""
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(downloaded=True, text=""),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is not None
    assert out.verdict == "retry"
    assert out.outcome == RETRY_ATTACH_FAILED


def test_rejudge_with_text_no_override():
    out = outcome_from_attach_rejudge_failure(
        AttachmentFetchResult(
            downloaded=True,
            text="ed2k://|file|x.mp4|1|ABCDEF0123456789ABCDEF0123456789|/",
        ),
        link_kind="ed2k",
        title="合集帖",
    )
    assert out is None
