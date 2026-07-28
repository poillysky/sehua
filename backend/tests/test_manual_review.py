# -*- coding: utf-8 -*-
"""人工已审：不合格 outcome 加前缀后移出待审列表。"""

from __future__ import annotations

from db.repository import (
    MANUAL_REVIEW_OUTCOME_PREFIX,
    MANUAL_REVIEW_TAG,
    _frame_fail_where,
    mark_frame_fail_manual_reviewed,
)
from parsers.unqual_outcomes import normalize_unqual_reason_kind


def test_normalize_strips_manual_review_prefix():
    assert (
        normalize_unqual_reason_kind(
            f"{MANUAL_REVIEW_OUTCOME_PREFIX}不合格：待核 · 【识别错误】漏链"
        )
        == "不合格：待核"
    )


def test_frame_fail_where_reviewed_vs_pending():
    pending_sql, pending_params = _frame_fail_where(status="all")
    assert "不合格%" in pending_params
    assert MANUAL_REVIEW_OUTCOME_PREFIX + "%" not in pending_params

    rev_sql, rev_params = _frame_fail_where(status="reviewed")
    assert any(
        isinstance(p, str) and p.startswith(MANUAL_REVIEW_OUTCOME_PREFIX)
        for p in rev_params
    )
    assert MANUAL_REVIEW_TAG in rev_params
    assert "人工已审" in rev_sql or "%s" in rev_sql


def test_mark_frame_fail_manual_reviewed_empty_tids():
    class Dummy:
        def cursor(self):
            raise AssertionError("should not touch db")

        def commit(self):
            raise AssertionError("should not commit")

    out = mark_frame_fail_manual_reviewed(Dummy(), tids=[])
    assert out["matched"] == 0
    assert out["updated"] == 0
