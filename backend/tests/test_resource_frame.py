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
    assert frame.spec.kind == "single_multi_link"
    assert frame.verdict.status == "ok"
    assert "verdict:ok" in frame.verdict.tags
    assert "kind:single_multi_link" in frame.verdict.tags
    assert len(frame.rows) == 1
    assert len(frame.rows[0].links) == 2
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("成功")
    assert "形态:单资源多链接" in text


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


def test_frame_shared_preview_structure_fail():
    img = ["http://same.jpg"]
    a = _asset("A" * 40, "甲", size=1, prev=img)
    b = _asset("B" * 40, "乙", size=1, prev=img)
    groups = [("甲", a, [a]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("双资源", [a, b]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert any("预览图完全相同" in e for e in frame.verdict.hard_errors)
    assert any("【识别错误】" in e for e in frame.verdict.hard_errors)
    assert frame.spec.kind == "multi_one_link"


def test_frame_title_count_structure_fail():
    a = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    groups = [("甲", a, [a]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("精选合集 ×5", [a, b]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert any("×5" in e for e in frame.verdict.hard_errors)


def test_frame_d1_content_gap_via_validate():
    """填槽后 size 仍为 0，但帖面有容量文案 → content_gap。"""
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
        kind="single_one_link",
        capacity="D1",
        source="body",
        layout="no_subtitle",
    )
    parsed = _parsed("片子", [a], description="【资源大小】：66.7GB")
    verdict = validate_frame(spec, [row], parsed, post_title="片子")
    assert verdict.status == "content_gap"
    assert "verdict:content_gap" in verdict.tags
    from parsers.resource_frame import ResourceFrame, format_frame_outcome

    text = format_frame_outcome(
        "成功：已提取主链",
        ResourceFrame(spec=spec, rows=[row], verdict=verdict),
    )
    assert text.startswith("不合格：容量")
    assert not text.startswith("成功")


def test_kind_multi_multi_link():
    a1 = _asset("A" * 40, "甲", size=1, prev=["http://a.jpg"])
    a2 = _asset("C" * 40, "甲", size=1)
    b = _asset("B" * 40, "乙", size=1, prev=["http://b.jpg"])
    groups = [("甲", a1, [a1, a2]), ("乙", b, [b])]
    frame = build_resource_frame(_parsed("双", [a1, a2, b]), named_groups=groups)
    assert frame.spec.kind == "multi_multi_link"
    assert "形态:多资源多链接" in format_frame_outcome("成功：已提取 2 条资源", frame)


def test_missing_preview_vs_parse_preview():
    a = _asset("A" * 40, "甲", size=1)
    b = _asset("B" * 40, "乙", size=1)
    groups = [("甲", a, [a]), ("乙", b, [b])]
    # 帖面也无图 → 真没有（软提醒，结构仍可通过，outcome 仍成功）
    frame = build_resource_frame(_parsed("双", [a, b]), named_groups=groups)
    assert any("【真没有】" in w and "预览" in w for w in frame.verdict.soft_warnings)
    assert frame.verdict.status == "ok"
    assert format_frame_outcome("成功：已提取 2 条资源", frame).startswith("成功")
    # 帖面有图却未分到名下 → 识别错误（结构不合格）
    parsed = _parsed("双", [a, b], preview_images=["http://t.jpg"])
    frame2 = build_resource_frame(parsed, named_groups=groups)
    assert frame2.verdict.status == "structure_fail"
    assert "flag:preview_fail" in frame2.verdict.tags
    assert any("【识别错误】" in e and "预览" in e for e in frame2.verdict.hard_errors)


def test_soft_parse_warning_is_review_not_clean_success():
    """结构过门但有【识别错误】软提醒 → 待核，勿进干净「成功」池。"""
    # 预览原图>5 截断为软提醒（硬门只卡截断后仍>5，填槽已截到5）
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
    assert any("【识别错误】" in w and "截断" in w for w in frame.verdict.soft_warnings)
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("待核")
    assert not text.startswith("成功")
    assert "verdict:review" in frame.verdict.tags


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


def test_ed2k_quota_mismatch_structure_fail():
    """ed2k：链数明显少于 N配额 → 结构不合格。"""
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
    assert frame.verdict.status == "structure_fail"
    assert any("20配额" in e and "链数" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：正文含目标链接", frame).startswith("不合格")


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


def test_magnet_v_mismatch_structure_fail():
    """磁力：链数明显少于标题 NV → 结构不合格。"""
    title = "精选合集 20V"
    a = _asset("A" * 40, "独立包名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "独立包名", size=1)
    groups = [("独立包名", a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert any("20V" in e or "漏链" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("不合格")


def test_magnet_v_match_ok_even_name_eq_title():
    """磁力：链数 ≥ NV，资源名=帖标题 → 合格。"""
    title = "国产合集 3V"
    links = [
        _asset(("A" * 39 + str(i))[-40:], title, size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    frame = build_resource_frame(_parsed(title, links), named_groups=[(title, links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_magnet_no_v_default_ok():
    """磁力：无 V 口径（仅有共N部）→ 不做强制数量判断，默认合格。"""
    title = "「磁力丨整理」国产AV 合集共50部【50部/1GB】"
    links = [
        _asset(("A" * 39 + str(i))[-40:], title, size=1, prev=["http://a.jpg"] if i == 0 else None)
        for i in range(3)
    ]
    frame = build_resource_frame(_parsed(title, links), named_groups=[(title, links[0], links)])
    assert frame.verdict.status == "ok"
    assert "info:no_v_skip_count" in frame.verdict.tags
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_multi_link_fewer_links_than_v_fail():
    """单资源多链接：链数明显少于标题 NV → 结构不合格。"""
    title = "精选合集 5V"
    a = _asset("A" * 40, "独立包名", size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "独立包名", size=1)
    groups = [("独立包名", a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.verdict.status == "structure_fail"
    assert any("漏链" in e or "链数" in e or "5V" in e for e in frame.verdict.hard_errors)


def test_collapsed_multi_name_not_fake_success():
    """标题×N 却只填出 1 名单链 → 不合格，禁止成功。"""
    title = "精选合集 ×3"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    groups = [(title, a, [a])]
    frame = build_resource_frame(_parsed(title, [a]), named_groups=groups)
    assert frame.spec.kind == "single_one_link"
    assert frame.verdict.status == "structure_fail"
    text = format_frame_outcome("成功：已提取主链", frame)
    assert text.startswith("不合格")
    assert any("1名单链" in e or "×3" in e for e in frame.verdict.hard_errors)


def test_single_multi_link_title_count_match_ok():
    """单资源多链接：磁力 NV 与链数相符（即使资源名=帖标题）→ 结构合格。"""
    title = "「磁力丨整理」国产AV 合集 3V【3部/1GB】"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, title, size=1)
    c = _asset("C" * 40, title, size=1)
    groups = [(title, a, [a, b, c])]
    frame = build_resource_frame(
        _parsed(title, [a, b, c]), named_groups=groups
    )
    assert frame.spec.kind == "single_multi_link"
    assert frame.verdict.status == "ok"
    assert "info:piece_count_match" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    text = format_frame_outcome("成功：附件解析出目标链接", frame)
    assert text.startswith("成功")
    assert not text.startswith("不合格")


def test_single_multi_link_more_links_than_v_ok():
    """单资源多链接：链数多于标题 NV → 仍结构合格。"""
    title = "「磁力丨整理」国产AV 合集 3V【3部/1GB】"
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
    """单资源多链接：资源名=帖标题（无 V/配额）→ 仍结构合格。"""
    title = "某某合集帖"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, title, size=1)
    groups = [(title, a, [a, b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.spec.kind == "single_multi_link"
    assert frame.verdict.status == "ok"
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert "info:no_v_skip_count" in frame.verdict.tags
    assert not frame.verdict.hard_errors
    assert format_frame_outcome("成功：已提取主链", frame).startswith("成功")


def test_single_multi_link_large_pack_962_ok():
    """大合集共962部 + 962链 + 资源名=帖标题、无 V → 默认合格（磁力无 V 不强制）。"""
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
    assert "info:no_v_skip_count" in frame.verdict.tags
    assert "info:pack_name_is_title" in frame.verdict.tags
    assert format_frame_outcome("成功：正常入库", frame).startswith("成功")


def test_multi_resource_name_eq_title_fail():
    """多资源：任一资源名=帖标题 → 结构不合格。"""
    title = "双资源合集帖"
    a = _asset("A" * 40, title, size=1, prev=["http://a.jpg"])
    b = _asset("B" * 40, "另一片名", size=1, prev=["http://b.jpg"])
    groups = [(title, a, [a]), ("另一片名", b, [b])]
    frame = build_resource_frame(_parsed(title, [a, b]), named_groups=groups)
    assert frame.spec.kind in {"multi_one_link", "multi_multi_link"}
    assert frame.verdict.status == "structure_fail"
    assert any("帖标题" in e for e in frame.verdict.hard_errors)
    assert format_frame_outcome("成功：已提取主链", frame).startswith("不合格")


def test_capacity_d1_flag():
    a = _asset("A" * 40, "合集", size=0, prev=["http://x.jpg"])
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
        SlotFill("size", False, "0", "parse", "有容量文案但大小为0"),
    ]
    spec = FrameSpec(
        shape="A",
        kind="single_one_link",
        capacity="D1",
        source="body",
    )
    v = validate_frame(
        spec,
        [row],
        _parsed("合集【66.7GB】", [a], description="【资源大小】：66.7GB"),
        post_title="合集【66.7GB】",
    )
    assert v.status == "content_gap"
    assert "flag:capacity_fail" in v.tags
    assert any("【识别错误】" in w for w in v.soft_warnings)


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

    # 多资源预览串名 → 结构不合格（仍写入）
    img = ["http://same.jpg"]
    a = _asset("A" * 40, "片子甲", size=1, prev=img)
    b = _asset("B" * 40, "片子乙", size=1, prev=img)
    a.is_primary = True
    parsed = _parsed("双资源帖", [a, b])
    out = persist_mod.persist_dual_parse(
        Conn(),
        parsed,
        source_url="https://example.com/thread-frame-1-1.html",
    )
    assert out["verdict"] == "structure_fail"
    assert out["import_outcome"].startswith("不合格")
    assert "verdict:structure_fail" in (out.get("parse_tags") or [])
    assert calls and str(calls[0]["import_outcome"]).startswith("不合格")
