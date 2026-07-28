"""不合格种类合并：资源名 / 链接 / 预览 / 容量。"""

from parsers.unqual_outcomes import (
    UNQUAL_CAPACITY,
    UNQUAL_LINK,
    UNQUAL_NAME,
    UNQUAL_PREVIEW,
    UNQUAL_REVIEW,
    classify_unqual_kind,
    normalize_unqual_reason_kind,
)


def test_classify_by_new_prefix():
    assert classify_unqual_kind(outcome="不合格：链接 · 形态:单资源多链接") == UNQUAL_LINK
    assert classify_unqual_kind(outcome="不合格：预览 · 原因:共享") == UNQUAL_PREVIEW
    assert classify_unqual_kind(outcome="不合格：资源名 · 原因:未切开") == UNQUAL_NAME
    assert classify_unqual_kind(outcome="不合格：容量 · 原因:写出了大小") == UNQUAL_CAPACITY
    assert classify_unqual_kind(outcome="不合格：待核 · 原因:配额") == UNQUAL_REVIEW
    assert classify_unqual_kind(outcome="待核：正文含目标链接 · 原因:x") == UNQUAL_REVIEW


def test_classify_kind_template_as_link():
    assert (
        classify_unqual_kind(
            status="structure_fail",
            errors=["【识别错误】定型为单资源单链接，但填出多条链（链形态不一致）"],
        )
        == UNQUAL_LINK
    )


def test_classify_old_structure_by_reason():
    assert (
        classify_unqual_kind(
            status="structure_fail",
            errors=["【识别错误】多资源预览图完全相同"],
        )
        == UNQUAL_PREVIEW
    )
    assert (
        classify_unqual_kind(
            status="structure_fail",
            errors=["【识别错误】链数不合规：识别到3条下载链，入库各子资源合计1条"],
        )
        == UNQUAL_LINK
    )
    assert (
        classify_unqual_kind(
            status="structure_fail",
            errors=["【识别错误】子名等于帖标题"],
        )
        == UNQUAL_NAME
    )


def test_classify_content_gap_capacity():
    assert (
        classify_unqual_kind(
            status="content_gap",
            errors=["【识别错误】容量不合规：帖子写14.80GB，入库资源写0.0MB"],
        )
        == UNQUAL_CAPACITY
    )


def test_normalize_old_structure_outcome():
    old = "不合格：结构 · 形态:多资源单链接 · 原因:【识别错误】多资源预览图完全相同"
    assert normalize_unqual_reason_kind(old) == UNQUAL_PREVIEW
    old_name = "不合格：结构 · 形态:单资源单链接 · 原因:【识别错误】标题写×3，实际入库1"
    assert normalize_unqual_reason_kind(old_name) == UNQUAL_NAME
    old_link = "不合格：结构 · 形态:单资源多链接 · 链数:10 · 原因:【识别错误】链数不合规"
    assert normalize_unqual_reason_kind(old_link) == UNQUAL_LINK
