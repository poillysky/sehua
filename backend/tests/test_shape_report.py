"""形态标记 / 子资源-总量对比 / 中文告警。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.shape_report import build_shape_report, format_outcome_with_tags


def _asset(h: str, name: str, *, size: int = 0, prev: list[str] | None = None) -> ParsedAsset:
    return ParsedAsset(
        link_kind="magnet",
        hash=h,
        filename=name,
        size=size,
        uri="magnet:?xt=urn:btih:" + h,
        preview_images=list(prev or []),
    )


def _parsed(title: str, assets: list[ParsedAsset], **kw) -> DualParseResult:
    return DualParseResult(
        tid=1,
        title=title,
        description=kw.get("description", ""),
        metadata=kw.get("metadata", {}),
        preview_images=[],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
        layout=kw.get("layout", ""),
        had_attachments=kw.get("had_attachments", False),
    )


def test_shape_a_pack_tags():
    a = _asset("A" * 40, "合集名", size=100, prev=["http://x/1.jpg"])
    b = _asset("B" * 40, "合集名", size=50)
    groups = [("合集名", a, [a, b])]
    rep = build_shape_report(
        _parsed("合集【13V 66.7GB】", [a, b]),
        named_groups=groups,
        layout="no_subtitle",
    )
    assert "shape:A" in rep.tags
    assert "links:multi" in rep.tags


def test_shape_b_title_vs_sub_label_capacity_zh():
    """多资源：标题容量 vs 各子资源文案合计不一致 → 漏资源名旁证。"""
    a = _asset("A" * 40, "片子甲", size=10 * 1024**3, prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=20 * 1024**3, prev=["http://b.jpg"])
    a.description = "【影片名称】：片子甲\n【影片大小】：10GB\n"
    b.description = "【影片名称】：片子乙\n【影片大小】：20GB\n"
    groups = [("片子甲", a, [a]), ("片子乙", b, [b])]
    rep = build_shape_report(
        _parsed(
            "双片合集 ×2【100GB】",
            [a, b],
            description=a.description + b.description,
            layout="names_then_links",
        ),
        named_groups=groups,
        layout="names_then_links",
    )
    assert "kind:multi" in rep.tags
    assert "warn:title_vs_sub_label_capacity" in rep.tags
    assert any("漏资源名" in w or "文案合计" in w for w in rep.warnings)
    assert rep.verdict == "structure_fail"
    assert "flag:needs_rule" in rep.tags


def test_shape_b_ignores_last_block_size_as_pack_total():
    """帖级【影片大小】=末块子资源大小时，不当总容量去对照合计（tid 26694474）。"""
    a = _asset("A" * 40, "甲", size=4 * 1024**3, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=8 * 1024**3, prev=["http://b.jpg"])
    groups = [("甲", a, [a]), ("乙", b, [b])]
    rep = build_shape_report(
        _parsed(
            "三十部合集",
            [a, b],
            metadata={"资源大小": "8G"},
            description="【影片大小】：8G",
            layout="title_then_magnet",
        ),
        named_groups=groups,
        layout="title_then_magnet",
    )
    assert "warn:size_sum_mismatch" not in rep.tags
    assert "warn:title_vs_sub_label_capacity" not in rep.tags
    assert rep.verdict != "content_gap" or "flag:capacity_fail" not in rep.tags
    assert not any("总容量" in w for w in rep.warnings)


def test_link_sum_mismatch_zh():
    a = _asset("A" * 40, "合集")
    b = _asset("B" * 40, "合集")
    c = _asset("C" * 40, "合集")
    groups = [("合集", a, [a, b])]
    rep = build_shape_report(_parsed("包", [a, b, c]), named_groups=groups)
    assert "warn:link_sum_mismatch" in rep.tags
    assert any("链数不合规" in w for w in rep.warnings)
    assert rep.verdict == "structure_fail"
    text = format_outcome_with_tags("成功：已提取主链", rep)
    assert text.startswith("不合格")
    assert "形态:单资源" in text
    assert "链数:2≠识别3" in text
    assert "【识别错误】" in text


def test_shared_preview_zh():
    img = ["http://same.jpg"]
    a = _asset("A" * 40, "甲", size=1, prev=img)
    b = _asset("B" * 40, "乙", size=1, prev=img)
    groups = [("甲", a, [a]), ("乙", b, [b])]
    rep = build_shape_report(_parsed("双资源", [a, b]), named_groups=groups)
    assert any("预览图完全相同" in w for w in rep.warnings)
    assert rep.verdict == "structure_fail"


def test_title_count_mismatch_zh():
    a = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    groups = [("甲", a, [a]), ("乙", b, [b])]
    rep = build_shape_report(_parsed("精选合集 ×5", [a, b]), named_groups=groups)
    assert "warn:title_count_mismatch" in rep.tags
    assert any("×5" in w and "入库2" in w for w in rep.warnings)
    assert rep.verdict == "structure_fail"

def test_link_sum_ok():
    a = _asset("A" * 40, "甲", prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", prev=["http://b.jpg"])
    groups = [("甲", a, [a]), ("乙", b, [b])]
    rep = build_shape_report(_parsed("双", [a, b]), named_groups=groups)
    assert "warn:link_sum_mismatch" not in rep.tags
    assert not any("链数不合规" in w for w in rep.warnings)
