"""资源形态填槽框架：定型 / 填槽 / 三种 verdict。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from parsers.resource_frame import (
    FrameRow,
    FrameSpec,
    build_resource_frame,
    format_frame_outcome,
    validate_frame,
)
from db import persist as persist_mod


def _asset(
    h: str,
    name: str,
    *,
    size: int = 0,
    prev: list[str] | None = None,
) -> ParsedAsset:
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
        preview_images=kw.get("preview_images", []),
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
        layout=kw.get("layout", ""),
        had_attachments=kw.get("had_attachments", False),
    )


def test_frame_a_ok_multi_link():
    sz = int(66.7 * 1024**3)
    a = _asset("A" * 40, "合集名", size=sz, prev=["http://x/1.jpg"])
    b = _asset("B" * 40, "合集名", size=sz // 2)
    groups = [("合集名", a, [a, b])]
    frame = build_resource_frame(
        _parsed("合集【66.7GB】", [a, b]),
        named_groups=groups,
        layout="no_subtitle",
    )
    assert frame.spec.shape == "A"
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "verdict:ok" in frame.verdict.tags
    assert "kind:single" in frame.verdict.tags
    assert len(frame.rows) == 1
    assert len(frame.rows[0].links) == 2
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("成功")
    assert "形态:单资源" in text


def test_frame_prefers_capacity_text_over_tiny_magnet_xl():
    """合集文案 55.1GB 时，勿被残缺 magnet xl（几十 MB）盖掉。"""
    tiny = 24 * 1024 * 1024
    a = _asset("A" * 40, "Eva合集", size=tiny, prev=["http://x/1.jpg"])
    b = _asset("B" * 40, "Eva合集", size=0)
    a.description = (
        "【资源名称】：欧美女优4K Eva【23V 55.1GB】\n"
        "【资源大小】：23V 55.1GB\n"
    )
    groups = [("Eva合集", a, [a, b])]
    frame = build_resource_frame(
        _parsed("欧美女优4K Eva【23V 55.1GB】", [a, b], description=a.description),
        named_groups=groups,
        layout="no_subtitle",
    )
    expect = int(55.1 * 1024**3)
    assert frame.rows[0].size == expect
    assert frame.rows[0].size > tiny * 10


def test_frame_link_mismatch_structure_fail():
    a = _asset("A" * 40, "合集")
    b = _asset("B" * 40, "合集")
    c = _asset("C" * 40, "合集")
    groups = [("合集", a, [a, b])]
    frame = build_resource_frame(_parsed("包", [a, b, c]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert "flag:structure_fail" in frame.verdict.tags
    assert "verdict:structure_fail" in frame.verdict.tags
    assert "cause:parse" in frame.verdict.tags
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("不合格")
    assert "成功" not in text.split("·")[0]
    assert any("【识别错误】" in e for e in frame.verdict.hard_errors)


def test_frame_shared_preview_not_structure_fail():
    """共享预览不再作合格硬门（靠切块/资源名）。"""
    img = ["http://same.jpg"]
    a = _asset("A" * 40, "甲", size=1, prev=img)
    b = _asset("B" * 40, "乙", size=1, prev=img)
    groups = [("甲", a, [a]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("双资源", [a, b]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert not any("预览图完全相同" in e for e in frame.verdict.hard_errors)
    assert "flag:preview_fail" not in frame.verdict.tags
    assert "info:shared_preview" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取", frame).startswith("成功")
    assert frame.spec.kind == "multi"


def test_frame_same_hash_shared_preview_not_hard_fail():
    """同 hash 被切成两名：预览相同不进硬门。"""
    img = ["http://same.jpg"]
    h = "F906A787B1A73B02CCD8CE62CF4FA19C"
    a = _asset(h, "甲：放课后", size=1, prev=img)
    b = _asset(h, "甲:放课后", size=1, prev=img)
    groups = [("甲：放课后", a, [a]), ("甲:放课后", b, [b])]
    frame = build_resource_frame(_parsed("单包", [a, b]), named_groups=groups)
    assert not any("预览图完全相同" in e for e in frame.verdict.hard_errors)
    assert "warn:shared_preview" not in frame.verdict.tags


def test_frame_title_count_structure_fail():
    a = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    groups = [("甲", a, [a]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("精选合集 ×5", [a, b]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert any("×5" in e and ("漏资源名" in e or "漏识别" in e or "切错" in e or "入库2" in e) for e in frame.verdict.hard_errors)


def test_multi_label_under_split_fail():
    """多资源：正文 3 个【影片名称】却只入库 2 名 → 漏识别。"""
    title = "三资源帖"
    desc = (
        "【影片名称】：甲\n【影片大小】：1G\n"
        "【影片名称】：乙\n【影片大小】：1G\n"
        "【影片名称】：丙\n【影片大小】：1G\n"
    )
    a = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    frame = build_resource_frame(
        _parsed(title, [a, b], description=desc),
        named_groups=[("甲", a, [a]), ("乙", b, [b])],
    )
    assert frame.spec.kind == "multi"
    assert frame.verdict.status == "structure_fail"
    assert "warn:multi_label_under_split" in frame.verdict.tags
    assert any("漏资源名" in e or "漏识别" in e for e in frame.verdict.hard_errors)


def test_multi_resource_missing_link_fail():
    """多资源：某个资源名下无链 → 漏识别。"""
    a = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    # 手工造一行无链
    from parsers.resource_frame import FrameRow, FrameSpec, validate_frame

    row_a = FrameRow(
        filename="甲",
        size=1,
        previews=["http://a.jpg"],
        links=[a.uri],
        hashes=[a.hash],
        head=a,
        members=[a],
    )
    row_b = FrameRow(
        filename="乙",
        size=1,
        previews=["http://b.jpg"],
        links=[],
        hashes=[],
        head=b,
        members=[b],
    )
    spec = FrameSpec(shape="B", kind="multi", capacity="D3", source="body")
    v = validate_frame(spec, [row_a, row_b], _parsed("双资源", [a, b]), post_title="双资源")
    assert v.status == "structure_fail"
    assert "warn:multi_resource_missing_link" in v.tags


def test_frame_d1_content_gap_via_validate():
    """单资源：有容量文案 + size=0 不再硬判容量。"""
    a = _asset("A" * 40, "片子", size=0, prev=["http://a.jpg"])
    row = FrameRow(
        filename="片子",
        size=0,
        previews=["http://a.jpg"],
        links=[a.uri],
        hashes=[a.hash],
        head=a,
        members=[a],
    )
    spec = FrameSpec(
        shape="A",
        kind="single",
        capacity="D1",
        source="body",
        layout="no_subtitle",
    )
    parsed = _parsed("片子【66.7GB】", [a], description="【资源大小】：66.7GB")
    verdict = validate_frame(spec, [row], parsed, post_title="片子【66.7GB】")
    assert verdict.status == "ok"
    assert "flag:capacity_fail" not in verdict.tags


def test_kind_multi():
    a1 = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    a2 = _asset("C" * 40, "甲", size=1)
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    groups = [("甲", a1, [a1, a2]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("双", [a1, a2, b]), named_groups=groups)
    assert frame.spec.kind == "multi"
    assert "形态:多资源" in format_frame_outcome("成功：已提取 2 条资源", frame)


def test_missing_preview_vs_parse_preview():
    a = _asset("A" * 40, "甲", size=1)
    b = _asset("B" * 40, "乙", size=1)
    groups = [("甲", a, [a]), ("乙", b, [b])]
    # 帖面也无图 → 成功（预览不计合格）
    frame = build_resource_frame(_parsed("双", [a, b]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert format_frame_outcome("成功：已提取 2 条资源", frame).startswith("成功")
    assert "flag:preview_fail" not in frame.verdict.tags
    # 帖面有图却未分到名下 → 仍成功（只记 info）
    parsed = _parsed("双", [a, b], preview_images=["http://t.jpg"])
    frame2 = build_resource_frame(parsed, named_groups=groups)
    assert frame2.verdict.status == "ok"
    assert "flag:preview_fail" not in frame2.verdict.tags
    assert format_frame_outcome("成功：已提取 2 条资源", frame2).startswith("成功")
    assert "info:preview_empty_rows" in frame2.verdict.tags


def test_preview_truncate_is_info_not_review():
    """预览>5 截到 5 张是产品上限，不因此标【识别错误】/不合格：待核。"""
    title = "精选合集"
    a = _asset(
        "A" * 40,
        "独立包名",
        size=1,
        prev=[f"http://a{i}.jpg" for i in range(6)],
    )
    groups = [("独立包名", a, [a])]
    frame = build_resource_frame(_parsed(title, [a]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert "info:preview_truncated" in frame.verdict.tags
    assert not any("截断" in w and "【识别错误】" in w for w in frame.verdict.soft_warnings)
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("成功")
    assert not text.startswith("不合格")


def _ed2k_asset(h: str, name: str, *, size: int = 0, prev: list[str] | None = None) -> ParsedAsset:
    return ParsedAsset(
        link_kind="ed2k",
        hash=h,
        filename=name,
        size=size,
        uri=f"ed2k://|file|{name}|{max(size, 1)}|{h}|/",
        preview_images=list(prev or []),
    )


def test_ed2k_piece_count_uses_quota_not_v():
    """ed2k：对照 N配额，勿因标题里的 NV 片数误报。"""
    title = "【ED2K丨整理】浅浅作品合集【20.2g/17V/2配额】"
    a = _ed2k_asset("A" * 32, title, size=1, prev=["http://a.jpg"])
    b = _ed2k_asset("B" * 32, title, size=1)
    groups = [(title, a, [a, b])]
    parsed = DualParseResult(
        tid=3134416,
        title=title,
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=[a, b],
        primary_link_kind="ed2k",
        layout="",
        had_attachments=False,
    )
    frame = build_resource_frame(parsed, named_groups=groups)
    assert frame.verdict.status == "ok"
    assert frame.verdict.metrics.get("title_quota_count") == 2
    assert frame.verdict.metrics.get("title_v_count") == 17
    assert "info:piece_count_match" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    assert format_frame_outcome("成功：正文含目标链接", frame).startswith("成功")


def test_ed2k_quota_mismatch_title_overclaim_soft():
    """ed2k：链数少于 N配额且无附件可补 → 软提醒 → 不合格：待核（非硬确认类）。"""
    title = "合集【10.0g/50V/20配额】"
    links = [
        _ed2k_asset(("C" * 31 + str(i))[-32:], "包", size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(2)
    ]
    parsed = DualParseResult(
        tid=2,
        title=title,
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=links,
        primary_link_kind="ed2k",
        layout="",
        had_attachments=False,
    )
    frame = build_resource_frame(parsed, named_groups=[("包", links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert any("20配额" in e or "20" in e for e in frame.verdict.soft_warnings)
    out = format_frame_outcome("成功：正文含目标链接", frame)
    assert out.startswith("不合格：待核") or out.startswith("成功")


def test_ed2k_no_quota_default_ok():
    """ed2k：无配额信息 → 不做强制数量判断，默认合格（即使有共N部）。"""
    title = "电驴合集共50部【10GB】"
    links = [
        _ed2k_asset(("D" * 31 + str(i))[-32:], title, size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    parsed = DualParseResult(
        tid=3,
        title=title,
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=links,
        primary_link_kind="ed2k",
        layout="",
        had_attachments=False,
    )
    frame = build_resource_frame(parsed, named_groups=[(title, links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_magnet_v_ignored_no_quota_ok():
    """磁力：仅有 NV、无配额 → 不做链数强制（V 不准），默认合格。"""
    title = "精选合集 20V"
    a = _asset("A" * 40, "独立包名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "独立包名", size=1)
    groups = [("独立包名", a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:magnet_v_soft" not in frame.verdict.tags
    assert not frame.verdict.hard_errors
    out = format_frame_outcome("成功：已提取主链", frame)
    assert out.startswith("成功")
    assert not out.startswith("不合格")


def test_magnet_quota_mismatch_soft():
    """磁力：标题有配额且链数不足 → 待核（与 ed2k 同一口径）。"""
    title = "精选合集【20V/5配额】"
    a = _asset("A" * 40, "独立包名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "独立包名", size=1)
    groups = [("独立包名", a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert any("5配额" in w or "5" in w for w in frame.verdict.soft_warnings)
    out = format_frame_outcome("成功：已提取主链", frame)
    assert out.startswith("不合格：待核")


def test_magnet_quota_match_ok_even_name_eq_title():
    """磁力：链数 ≥ 配额（V≠配额），资源名=帖标题 → 合格。"""
    title = "国产合集【30V/3配额】"
    links = [
        _asset(("A" * 39 + str(i))[-40:], title, size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    frame = build_resource_frame(_parsed(title, links), named_groups=[(title, links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_magnet_no_quota_default_ok():
    """磁力：无配额（仅有共N部/NV）→ 不做强制数量判断，默认合格。"""
    title = "「磁力丨整理」国产AV 合集共50部【50部/1GB】"
    links = [
        _asset(("A" * 39 + str(i))[-40:], title, size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    frame = build_resource_frame(_parsed(title, links), named_groups=[(title, links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_multi_link_v_only_no_force():
    """单资源多链接磁力：仅 NV 无配额 → 不强制，不待核。"""
    title = "精选合集 5V"
    a = _asset("A" * 40, "独立包名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "独立包名", size=1)
    groups = [("独立包名", a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:magnet_v_soft" not in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_xn_title_no_hard_fail():
    """单资源：标题×N 不做切开硬判（合集标题党常见）。"""
    title = "精选合集 ×3"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    groups = [(title, a, [a])]
    frame = build_resource_frame(_parsed(title, [a]), named_groups=groups)
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert not any("未切开" in e or "×3" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_one_link_quota_mismatch_soft():
    """单资源单链接：标题 V≠配额且链不足 → 待核（V≈配额回声见 test_quota_echoes_v）。"""
    title = "合集【10G/50V/3配额】"
    a = _ed2k_asset("A" * 32, title, size=1, prev=["http://a.jpg"])
    frame = build_resource_frame(
        DualParseResult(
            tid=11,
            title=title,
            description="",
            metadata={},
            preview_images=["http://a.jpg"],
            extract_password="",
            assets=[a],
            primary_link_kind="ed2k",
            layout="",
            had_attachments=False,
        ),
        named_groups=[(title, a, [a])],
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "info:title_quota_overclaim_soft" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("不合格：待核")


def test_single_one_link_quota_echoes_v_ok():
    """单链 + 22V/22配额 + size≈标题容量 → 片数回声，勿待核（tid=3136385）。"""
    title = "【搬运】【115eD2K】Hamezo 合集【235G/22V/22配额】"
    a = _ed2k_asset("A" * 32, "Hamezo", size=int(235 * 1024**3), prev=["http://a.jpg"])
    frame = build_resource_frame(
        DualParseResult(
            tid=3136385,
            title=title,
            description="【资源大小】：235G/22V/22配额",
            metadata={},
            preview_images=["http://a.jpg"],
            extract_password="",
            assets=[a],
            primary_link_kind="ed2k",
            layout="",
            had_attachments=True,
        ),
        named_groups=[("Hamezo", a, [a])],
        had_attachments=True,
    )
    assert "info:pack_quota_soft" in frame.verdict.tags
    assert format_frame_outcome("成功：附件解析出目标链接", frame).startswith("成功")


def test_title_count_over_names_not_hard_fail():
    """多资源：入库名数 > 标题×N → 不是漏名，勿结构失败（tid=23485940）。"""
    assets = [
        _asset(f"{i:040X}", f"片{i}", size=1, prev=[f"http://{i}.jpg"])
        for i in range(5)
    ]
    groups = [(f"片{i}", a, [a]) for i, a in enumerate(assets)]
    frame = build_resource_frame(
        _parsed("精选合集 ×3", assets), named_groups=groups
    )
    assert frame.spec.kind == "multi"
    assert frame.verdict.status == "ok"
    assert "info:title_count_over_names" in frame.verdict.tags
    assert "warn:title_count_mismatch" not in frame.verdict.tags
    assert not any("漏资源名" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_multi_link_quota_match_ok():
    """单资源多链接：V≠配额且链数=配额 → piece_count_match。"""
    title = "「磁力丨整理」国产AV 合集【30V/3配额】"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, title, size=1)
    c = _asset("C" * 40, title, size=1)
    groups = [(title, a, [a, b, c])]
    frame = build_resource_frame(
        _parsed(title, [a, b, c]), named_groups=groups
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    text = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert text.startswith("成功")
    assert not text.startswith("不合格")


def test_single_multi_link_more_links_than_quota_ok():
    """单资源多链接：链数多于标题配额（V≠配额）→ 仍结构合格。"""
    title = "「磁力丨整理」国产AV 合集【30V/3配额】"
    links = [
        _asset(
            ("A" * 39 + str(i)),
            title,
            size=1,
            prev=["http://a.jpg"] if i == 0 else None,
        )
        for i in range(5)
    ]
    groups = [(title, links[0], links)]
    frame = build_resource_frame(_parsed(title, links), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_multi_link_title_as_name_ok_for_pack():
    """单资源多链接：资源名=帖标题（无配额）→ 仍结构合格。"""
    title = "某某合集帖"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, title, size=1)
    groups = [(title, a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_multi_link_large_pack_962_ok():
    """大合集共962部 + 962链 + 资源名=帖标题、无配额 → 默认合格（不强制）。"""
    title = "「磁力丨整理」国产AV 番号XB合集更新至1658共962部【962部/1006"
    links = [
        _asset(
            ("A" * 39 + f"{i:04d}")[-40:],
            title,
            size=1,
            prev=["http://a.jpg"] if i == 0 else None,
        )
        for i in range(962)
    ]
    groups = [(title, links[0], links)]
    frame = build_resource_frame(_parsed(title, links), named_groups=groups)
    assert frame.verdict.status == "ok"
    assert frame.verdict.metrics.get("title_expect_n") == 962
    assert "info:no_quota_skip_count" in frame.verdict.tags
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert format_frame_outcome("成功：正常入库", frame).startswith("成功")


def test_multi_resource_name_eq_title_fail():
    """多资源：任一资源名=帖标题 → 结构不合格。"""
    title = "双资源合集帖"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "另一片名", size=1, prev=["http://b.jpg"])
    groups = [(title, a, [a]), ("另一片名", b, [b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.spec.kind == "multi"
    assert frame.verdict.status == "structure_fail"
    assert any("帖标题" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("不合格")


def test_capacity_d1_flag_ed2k():
    """单资源 ed2k：有容量文案但 size=0 → 不再判容量不合格。"""
    a = _ed2k_asset("A" * 32, "合集", size=0, prev=["http://x.jpg"])
    row = FrameRow(
        filename="合集",
        size=0,
        previews=["http://x.jpg"],
        links=[a.uri],
        hashes=[a.hash],
        head=a,
        members=[a],
        slots=[],
    )
    from parsers.resource_frame import SlotFill

    row.slots = [
        SlotFill("filename", True, "合集"),
        SlotFill("links", True, "1条"),
        SlotFill("previews", True, "1张"),
        SlotFill("size", True, "0", "missing", "未用链上容量核验，允许0"),
    ]
    spec = FrameSpec(
        shape="A",
        kind="single",
        capacity="D1",
        source="body",
    )
    v = validate_frame(
        spec,
        [row],
        DualParseResult(
            tid=1,
            title="合集【66.7GB】",
            description="【资源大小】：66.7GB",
            metadata={},
            preview_images=[],
            extract_password="",
            assets=[a],
            primary_link_kind="ed2k",
            layout="",
            had_attachments=False,
        ),
        post_title="合集【66.7GB】",
    )
    assert v.status == "ok"
    assert "flag:capacity_fail" not in v.tags


def test_multi_title_vs_sub_label_capacity_mismatch():
    """多资源：标题容量 vs 各子资源文案合计不一致 → 漏识别硬门。"""
    title = "双资源合集【20GB】"
    a = _asset("A" * 40, "片子甲", size=int(1 * 1024**3), prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=int(2 * 1024**3), prev=["http://b.jpg"])
    a.description = "【影片名称】：片子甲\n【影片大小】：1GB\n"
    b.description = "【影片名称】：片子乙\n【影片大小】：2GB\n"
    desc = a.description + b.description
    frame = build_resource_frame(
        _parsed(title, [a, b], description=desc),
        named_groups=[("片子甲", a, [a]), ("片子乙", b, [b])],
    )
    assert frame.spec.kind == "multi"
    assert frame.verdict.status == "structure_fail"
    assert "warn:title_vs_sub_label_capacity" in frame.verdict.tags
    assert any("漏资源名" in e or "漏识别" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("不合格")


def test_multi_title_vs_sub_label_capacity_match_ok():
    """多资源：标题容量 = 各子资源文案合计 → 通过。"""
    title = "双资源合集【3GB】"
    a = _asset("A" * 40, "片子甲", size=int(1 * 1024**3), prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=int(2 * 1024**3), prev=["http://b.jpg"])
    a.description = "【影片名称】：片子甲\n【影片大小】：1GB\n"
    b.description = "【影片名称】：片子乙\n【影片大小】：2GB\n"
    desc = a.description + b.description
    frame = build_resource_frame(
        _parsed(title, [a, b], description=desc),
        named_groups=[("片子甲", a, [a]), ("片子乙", b, [b])],
    )
    assert frame.verdict.status == "ok"
    assert "info:title_sub_label_capacity_match" in frame.verdict.tags
    assert "info:multi_resources_recognized" in frame.verdict.tags


def test_single_multi_no_capacity_judge_even_if_mismatch():
    """单资源多链接：标题/正文容量冲突也不判（只做多资源文案对照）。"""
    title = "合集包【50GB】"
    links = [
        _ed2k_asset(
            ("E" * 31 + str(i))[-32:],
            title,
            size=0,
            prev=["http://a.jpg"] if i == 0 else None,
        )
        for i in range(3)
    ]
    frame = build_resource_frame(
        DualParseResult(
            tid=9,
            title=title,
            description="【资源大小】：10GB",
            metadata={"资源大小": "10GB"},
            preview_images=["http://a.jpg"],
            extract_password="",
            assets=links,
            primary_link_kind="ed2k",
            layout="",
            had_attachments=False,
        ),
        named_groups=[(title, links[0], links)],
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "flag:capacity_fail" not in frame.verdict.tags


def test_persist_structure_fail_outcome(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)
    monkeypatch.setattr(persist_mod, "delete_stub_by_source_url", lambda *a, **k: False)
    monkeypatch.setattr(persist_mod, "sync_board_meta_by_source_url", lambda *a, **k: 0)
    monkeypatch.setattr(
        persist_mod, "delete_other_resources_by_source_url", lambda *a, **k: 0
    )

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append(
            {
                "import_outcome": kwargs.get("import_outcome"),
                "parse_tags": kwargs.get("parse_tags"),
            }
        )
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)

    class Conn:
        def commit(self):
            pass

        def rollback(self):
            pass

    # 多资源标题 ×N 与入库名数不符 → 结构不合格（仍写入）；预览不再作硬门
    a = _asset("A" * 40, "片子甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=1, prev=["http://b.jpg"])
    a.is_primary = True
    parsed = _parsed("精选合集 ×5", [a, b])
    out = persist_mod.persist_dual_parse(
        Conn(),
        parsed,
        source_url="https://example.com/thread-frame-1-1.html",
    )
    assert out["verdict"] == "structure_fail"
    assert out["import_outcome"].startswith("不合格")
    assert "verdict:structure_fail" in (out.get("parse_tags") or [])
    assert calls and str(calls[0]["import_outcome"]).startswith("不合格")


def test_x3p_not_title_expect_count():
    """Sara x Rio x 3P 是玩法，不是 ×3 资源。"""
    from parsers.resource_frame import _title_expect_count

    title = "【搬运】【磁力】FC2PPV 4873635 [花絮] Sara x Rio x 3P，内射【7.22GB/1V】"
    assert _title_expect_count(title) is None
    a = _asset("A" * 40, "FC2PPV 4873635", size=int(7.22 * 1024**3), prev=["http://a.jpg"])
    frame = build_resource_frame(_parsed(title, [a]), named_groups=[(a.filename, a, [a])])
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert not any("子名未切开" in e for e in frame.verdict.hard_errors)


def test_film_and_resource_name_labels_not_multi():
    """单包模板并列【影片名称】+【资源名称】≠应收多资源。"""
    title = "2048独家合集 King8【若涵】第2期 4K 无水印【18.5G/20V】"
    desc = (
        "【影片名称】：2048独家合集 King8【若涵】第2期 4K 无水印【18.5G/20V】\n"
        "【影片大小】：18.5G/20V\n"
        "【资源名称】：King8【若涵】第2期 4K 无水印\n"
        "【资源类型】：视频\n"
    )
    sz = int(18.5 * 1024**3)
    a = _asset("A" * 40, title, size=0, prev=["http://a.jpg"])
    a.description = desc
    frame = build_resource_frame(
        _parsed(title, [a], description=desc),
        named_groups=[(title, a, [a])],
    )
    assert frame.verdict.status == "ok"
    assert not any("资源名称标签" in e for e in frame.verdict.hard_errors)
    assert frame.rows[0].size == sz


def test_repeated_film_name_labels_ok_for_single():
    """名数=1 但正文两个不同【影片名称】= 多资源漏切成单名 → 不合格：资源名。"""
    title = "合集帖"
    desc = "【影片名称】：甲\n【影片大小】：1G\n【影片名称】：乙\n【影片大小】：2G\n"
    a = _asset("A" * 40, "甲", size=int(1 * 1024**3), prev=["http://a.jpg"])
    frame = build_resource_frame(
        _parsed(title, [a], description=desc),
        named_groups=[("甲", a, [a])],
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "structure_fail"
    assert "info:multi_label_skip_single" in frame.verdict.tags
    assert "warn:split_collapse_suspect" in frame.verdict.tags
    assert any("漏切成单名" in e for e in frame.verdict.hard_errors)
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("不合格：资源名")
    assert "形态:单资源" in text


def test_nested_duplicate_film_name_label_not_split_collapse():
    """嵌套重复【影片名称】：同值 → 不当事漏切（tid=2156323）。"""
    title = "【影片名称】：真实良家偷拍，【推油少年】，女大学生"
    desc = (
        "【影片名称】：【影片名称】：真实良家偷拍，【推油少年】，女大学生\n"
        "【影片大小】：677M\n"
    )
    a = _asset("A" * 40, title, size=int(677 * 1024**2), prev=["http://a.jpg"])
    frame = build_resource_frame(
        _parsed(title, [a], description=desc),
        named_groups=[(title, a, [a])],
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "warn:split_collapse_suspect" not in frame.verdict.tags
    assert "info:multi_label_same_value" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_title_xn_single_collapse_soft():
    """标题×N 只表示包内片数：单资源不因此软待核。"""
    title = "精选合集 ×3"
    a = _asset("A" * 40, "合集包", size=1, prev=["http://a.jpg"])
    frame = build_resource_frame(
        _parsed(title, [a]),
        named_groups=[("合集包", a, [a])],
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert "warn:split_collapse_suspect" not in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_multi_weak_short_name_fail():
    """多资源：弱名（单字母等）→ 漏识别硬判。"""
    a = _asset("A" * 40, "甲影片名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "A", size=1, prev=["http://b.jpg"])
    frame = build_resource_frame(
        _parsed("双资源", [a, b]),
        named_groups=[("甲影片名", a, [a]), ("A", b, [b])],
    )
    assert frame.spec.kind == "multi"
    assert frame.verdict.status == "structure_fail"
    assert "warn:weak_subresource_name" in frame.verdict.tags
    assert any("过短或占位" in e for e in frame.verdict.hard_errors)


def test_multi_short_cjk_name_ok():
    """多资源：2～3 字中文短片名可保留，不视为弱名。"""
    a = _asset("A" * 40, "油鬼子", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=1, prev=["http://b.jpg"])
    frame = build_resource_frame(
        _parsed("双资源", [a, b]),
        named_groups=[("油鬼子", a, [a]), ("片子乙", b, [b])],
    )
    assert frame.spec.kind == "multi"
    assert "warn:weak_subresource_name" not in frame.verdict.tags
    assert frame.verdict.status == "ok"


def test_empty_size_label_allows_zero():
    """【影片大小】：MB（无数字）→ 允许 size=0，不升容量不合格。"""
    title = "国产合集 [07.08]"
    a = _asset("A" * 40, "片子甲", size=int(500 * 1024**2), prev=["http://a.jpg"])
    b = _asset("B" * 40, "片子乙", size=0, prev=["http://b.jpg"])
    b.description = "【影片名称】：片子乙\n【影片大小】：MB\n【影片格式】：MP4\n"
    a.description = "【影片名称】：片子甲\n【影片大小】：500MB\n"
    frame = build_resource_frame(
        _parsed(title, [a, b], description=a.description + "\n" + b.description),
        named_groups=[("片子甲", a, [a]), ("片子乙", b, [b])],
    )
    assert frame.verdict.status == "ok"
    assert not any("大小为0" in (w or "") for w in frame.verdict.soft_warnings)
    assert frame.rows[1].size == 0


def test_magnet_no_xl_skips_capacity_hard_fail():
    """磁力无 xl 且 size=0：单资源多链接不做容量硬判。"""
    title = "欧美合集【23V 28.1GB】"
    links = [
        _asset(("A" * 39 + str(i))[-40:], title, size=0, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    from parsers.resource_frame import FrameRow, FrameSpec, SlotFill, validate_frame

    row = FrameRow(
        filename=title,
        size=0,
        previews=["http://a.jpg"],
        links=[x.uri for x in links],
        hashes=[x.hash for x in links],
        head=links[0],
        members=links,
        slots=[
            SlotFill("filename", True, title[:40]),
            SlotFill("links", True, "3条"),
            SlotFill("previews", True, "1张"),
            SlotFill("size", True, "0", "missing", "未用链上容量核验，允许0"),
        ],
    )
    spec = FrameSpec(
        shape="A",
        kind="single",
        capacity="D1",
        source="body",
    )
    v = validate_frame(spec, [row], _parsed(title, links), post_title=title)
    assert v.status == "ok"
    assert "flag:capacity_fail" not in v.tags


def test_pack_size_prefers_gb_over_v_count():
    """【337V/640G】容量取 640G，勿把 337V 当 GB。"""
    from parsers.magnet import parse_capacity_bytes

    title = "【115ED2K】【FootsieBabes 合集】【337V/640G/4配额】"
    assert parse_capacity_bytes(title) == 640 * 1024**3
    links = []
    per = int((640 * 1024**3) / 4)
    for i in range(4):
        links.append(
            _ed2k_asset(
                ("F" * 31 + str(i))[-32:],
                title,
                size=per,
                prev=["http://a.jpg"] if i == 0 else None,
            )
        )
    frame = build_resource_frame(
        DualParseResult(
            tid=2770663,
            title=title,
            description="",
            metadata={},
            preview_images=[],
            extract_password="",
            assets=links,
            primary_link_kind="ed2k",
            layout="",
            had_attachments=False,
        ),
        named_groups=[(title, links[0], links)],
    )
    assert frame.rows[0].size >= int(640 * 1024**3 * 0.95)
    assert frame.verdict.status == "ok"


def test_minor_missing_preview_not_unqual():
    """多资源缺预览不计合格；outcome 成功。"""
    assets = []
    groups = []
    for i in range(8):
        name = f"片子{i}"
        prev = [] if i == 7 else [f"http://p/{i}.jpg"]
        a = _asset(("X" * 39 + str(i))[-40:], name, size=1024**3, prev=prev)
        assets.append(a)
        groups.append((name, a, [a]))
    frame = build_resource_frame(
        _parsed("合集", assets, preview_images=["http://thread.jpg"]),
        named_groups=groups,
    )
    assert frame.verdict.status == "ok"
    assert "warn:preview_unassigned_minor" not in frame.verdict.tags
    assert not frame.verdict.hard_errors
    assert not any("预览" in str(w) for w in frame.verdict.soft_warnings)
    out = format_frame_outcome("成功：已提取", frame)
    assert out.startswith("成功")
    assert "不合格" not in out.split("·")[0]


def test_n_bu_heji_not_title_expect_count():
    """「6部合集」是包内片数/片名，不是 ×6 资源名（常配 1配额单链）。"""
    from parsers.resource_frame import _title_expect_count

    title = "【自转】【百度/115eD2k】付费6部合集（第1弹）绿帽夫妻【6V/6.8GB/1配额】"
    assert _title_expect_count(title) is None
    sz = int(6.8 * 1024**3)
    a = _asset("A" * 40, "mike412约炮合集", size=sz, prev=["http://a.jpg"])
    a.link_kind = "ed2k"
    a.uri = f"ed2k://|file|pack.rar|{sz}|{'AA'*16}|/"
    frame = build_resource_frame(
        _parsed(title, [a], had_attachments=True),
        named_groups=[(a.filename, a, [a])],
        had_attachments=True,
    )
    assert frame.spec.kind == "single"
    assert frame.verdict.status == "ok"
    assert not any("子名未切开" in e for e in frame.verdict.hard_errors)


def test_placeholder_size_uses_xl_sum():
    """入库 size=4KB 占位时，用 ed2k xl 合计对照帖称容量。"""
    from parsers.ed2k import size_from_ed2k_uri

    title = "【自转】【ed2k】蓝光合集【4V/214G/4配额】"
    pack = int(214 * 1024**3)
    xl = pack // 4
    assets = []
    for i in range(4):
        h = f"{i:02x}" * 16
        a = ParsedAsset(
            link_kind="ed2k",
            hash=h,
            filename="蓝光合集",
            size=4096,
            uri=f"ed2k://|file|p{i}.rar|{xl}|{h}|/",
            preview_images=["http://a.jpg"] if i == 0 else [],
        )
        a.size = size_from_ed2k_uri(a.uri) or a.size
        assets.append(a)
    parsed = _parsed(title, assets)
    parsed.primary_link_kind = "ed2k"
    frame = build_resource_frame(
        parsed, named_groups=[("蓝光合集", assets[0], assets)]
    )
    assert frame.verdict.status == "ok"
    assert not any("容量不合规" in e for e in frame.verdict.hard_errors)
    assert not any("容量不合规" in e for e in frame.verdict.soft_warnings)


def test_resolution_wxh_not_title_expect_count():
    """【分辨率】1024X576至2048X1152 不是 ×1152 资源（tid=27124261）。"""
    from parsers.resource_frame import _title_expect_count

    title = "2048独家合集 91【大汉刘备】（60）坦克【1V/4.37G/36分/2K】"
    desc = (
        "【影片名称】：" + title + "\n"
        "【影片大小】：4.37G\n"
        "【分辨率】：1024X576至2048X1152\n"
        "【资源数量】：1\n"
    )
    assert _title_expect_count(title) is None
    # 即使传入 desc 也忽略（总资源数只匹配标题）
    assert _title_expect_count(title, desc) is None


def test_times_xn_ci_not_title_expect_count():
    """片名「365天×10次」不是 ×10 资源。"""
    from parsers.resource_frame import _title_expect_count

    title = (
        "2048独家合集 MIDV-387 小野六花 365天×10次连续射精的我…【1V/19G/118分/4K】"
    )
    assert _title_expect_count(title) is None


def test_desc_censored_name_x_age_not_title_expect_count():
    """正文「楊x 23 c罩杯」不参与总资源数；只匹配标题（tid=23485940）。"""
    from parsers.resource_frame import _title_expect_count

    title = "★★最强優片★★最強國產專輯A♂[12.27 ]"
    desc = (
        "【资源名称】：重慶xx職業學院 楊x 23 c罩杯 在讀學生\n"
        "共 50 部合集\n"
        "【资源类型】：MP4\n"
    )
    assert _title_expect_count(title) is None
    assert _title_expect_count(title, desc) is None
    assert _title_expect_count("合集 x 23个资源") == 23

