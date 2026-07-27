"""子资源 filename：【影片名称】/【资源名称】，不是 ed2k/dn 链内名。"""

from __future__ import annotations

from parsers.resource_names import (
    filename_from_link,
    is_missing_filename,
    resolve_sub_filename,
    subtitle_from_description,
)


def test_missing_placeholder_magnet():
    assert is_missing_filename("magnet-A14DF085", hash_value="A14DF0858322")
    assert is_missing_filename("", hash_value="ABC")
    assert is_missing_filename(
        "ABCDEFabcdefABCDEF0123456789ABCDEF01234567",
        hash_value="ABCDEFabcdefABCDEF0123456789ABCDEF01234567",
    )
    assert not is_missing_filename("片子A.mp4")
    assert not is_missing_filename("国产合集.rar")


def test_resolve_keeps_subresource_title():
    assert (
        resolve_sub_filename(
            inner_name="【合集】片子甲",
            title="合集帖标题",
            hash_value="A" * 40,
            link_uri="ed2k://|file|inner.mp4|1|" + "A" * 32 + "|/",
        )
        == "【合集】片子甲"
    )


def test_resolve_rejects_ed2k_embedded_name():
    uri = "ed2k://|file|alone.mp4|9|" + "C" * 32 + "|/"
    assert (
        resolve_sub_filename(
            inner_name="alone.mp4",
            title="单资源帖",
            hash_value="C" * 32,
            link_uri=uri,
        )
        == "单资源帖"
    )


def test_resolve_uses_description_subtitle():
    uri = "ed2k://|file|pack.rar|9|" + "C" * 32 + "|/"
    assert (
        resolve_sub_filename(
            inner_name="pack.rar",
            title="帖子标题",
            hash_value="C" * 32,
            link_uri=uri,
            description="【资源名称】真·资源名\n【资源大小】1G",
        )
        == "真·资源名"
    )


def test_subtitle_from_description_prefers_film():
    assert (
        subtitle_from_description("【资源名称】甲\n【影片名称】乙")
        == "乙"
    )


def test_pick_keeps_nested_decorative_brackets():
    """片名里的【S级泄密】等装饰标签不得截断取值。"""
    from parsers.content import _subresource_title_value, extract_metadata
    from parsers.resource_names import pick_subresource_title

    text = (
        "【影片名称】：??【S级泄密】姿势很多的反差少妇露脸性爱，"
        "床上各种高潮脸窒息吐舌阿黑颜，无套中出母狗呻吟享受，原档无水印(22V)\n"
        "【影片格式】：MP4\n"
        "【影片大小】：917MB\n"
        "【影片时间】：34:25\n"
        "【影片说明】：无码\n"
        "【影片截图】："
    )
    want = (
        "??【S级泄密】姿势很多的反差少妇露脸性爱，"
        "床上各种高潮脸窒息吐舌阿黑颜，无套中出母狗呻吟享受，原档无水印(22V)"
    )
    assert pick_subresource_title(text, prefer_last=False) == want
    assert extract_metadata(text).get("影片名称") == want
    assert _subresource_title_value(text, 6, len(text)) == want


def test_pick_keeps_various_decorative_prefixes_and_brackets():
    """?? ※ ★ ！！ 全角？？ 以及异写括号字段，片名应完整保留。"""
    from parsers.content import extract_metadata
    from parsers.resource_names import pick_subresource_title

    cases = [
        (
            "【影片名称】：※※【内部流出】样片名甲\n［影片格式］：MP4\n",
            "※※【内部流出】样片名甲",
        ),
        (
            "【影片名称】：！！【S级】样片名乙\n「影片大小」：1.2GB\n",
            "！！【S级】样片名乙",
        ),
        (
            "［影片名称］：？？『黑料』样片名丙\n【影片说明】：无码\n",
            "？？『黑料』样片名丙",
        ),
        (
            "『资源名称』：★★【自转】合集丁(12V)\n【资源类型】：视频\n",
            "★★【自转】合集丁(12V)",
        ),
        (
            "【影片名称】:◆◆【完结】尾声戊\n【影片预览】：\n",
            "◆◆【完结】尾声戊",
        ),
    ]
    for text, want in cases:
        assert pick_subresource_title(text, prefer_last=False) == want, text
        meta = extract_metadata(text)
        got = meta.get("影片名称") or meta.get("资源名称")
        assert got == want, text


def test_resolve_falls_back_to_title():
    assert (
        resolve_sub_filename(
            inner_name="magnet-A14DF085",
            title="【BT】合集帖",
            hash_value="A14DF0858322ABCD",
        )
        == "【BT】合集帖"
    )


def test_filename_from_ed2k_link():
    uri = "ed2k://|file|demo视频.mp4|12345|AAAABBBBCCCCDDDDEEEEFFFF00001111|/"
    assert filename_from_link(uri) == "demo视频.mp4"


def test_persist_multi_and_single_naming(monkeypatch):
    from parsers.links import DualParseResult, ParsedAsset
    from db import persist as persist_mod

    class _Conn:
        def commit(self):
            return None

        def rollback(self):
            return None

    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)
    monkeypatch.setattr(persist_mod, "delete_stub_by_source_url", lambda *a, **k: False)
    monkeypatch.setattr(persist_mod, "sync_board_meta_by_source_url", lambda *a, **k: 0)

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append(
            {
                "filename": link.filename,
                "title": kwargs.get("title"),
                "hash": link.hash,
            }
        )
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)

    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename="片子甲真名",
            size=1,
            uri="magnet:?xt=urn:btih:" + "A" * 40 + "&dn=子文件A.mp4",
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename="magnet-BBBBBBBB",
            size=1,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
            is_primary=False,
        ),
    ]
    parsed = DualParseResult(
        tid=1,
        title="合集标题",
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=assets,
        primary_link_kind="magnet",
    )
    out = persist_mod.persist_dual_parse(
        _Conn(), parsed, source_url="https://x/thread-1-1-1.html"
    )
    assert out["count"] == 2
    assert calls[0]["title"] == "合集标题"
    assert calls[0]["filename"] == "片子甲真名"
    assert calls[1]["title"] == "合集标题"
    assert calls[1]["filename"] == "合集标题"  # 无名 → 标题

    calls.clear()
    alone = ParsedAsset(
        link_kind="ed2k",
        hash="C" * 32,
        filename="alone.mp4",
        size=9,
        uri="ed2k://|file|alone.mp4|9|" + "C" * 32 + "|/",
        is_primary=True,
    )
    parsed2 = DualParseResult(
        tid=2,
        title="单资源帖",
        description="",
        metadata={},
        preview_images=[],
        extract_password="",
        assets=[alone],
        primary_link_kind="ed2k",
    )
    persist_mod.persist_dual_parse(
        _Conn(), parsed2, source_url="https://x/thread-2-1-1.html"
    )
    assert calls[0]["title"] == "单资源帖"
    # ed2k 链内名不是子资源名 → 退回主标题
    assert calls[0]["filename"] == "单资源帖"


def test_resolve_rejects_html_bbcode_and_intro_tail():
    from parsers.resource_names import (
        clip_subresource_display_name,
        is_dirty_filename,
        resolve_sub_filename,
    )

    htmlish = (
        '[url]www.98T.la@CLA96-Ai.mp4[/" target="_blank">'
        '<span class="__cf_email__" data-cfemail="abc">x</span></a>'
    )
    assert is_dirty_filename(htmlish)
    assert (
        resolve_sub_filename(
            inner_name=htmlish,
            title="【整理】cla合集标题",
            hash_value="A" * 40,
        )
        == "【整理】cla合集标题"
    )

    intro = (
        "《一半海水一半火焰》 【资源介绍】：看这部片子之前，我被朋友郑重告诫，"
        + ("很长正文" * 40)
    )
    clipped = clip_subresource_display_name(intro)
    assert clipped == "《一半海水一半火焰》"
    assert "资源介绍" not in clipped

    attach_ui = (
        "20e90e4390086.gif (1.63 MB, 下载次数: 0) 下载附件 2024-08-04 18:32 上传 "
        "c2ce21c5e77f2.gif (1.48 MB, 下载次数: 0)"
    )
    assert (
        resolve_sub_filename(
            inner_name=attach_ui,
            title="果冻传媒-性感女外教",
            hash_value="B" * 40,
        )
        == "果冻传媒-性感女外教"
    )

    jp = (
        "BD-M01 中出世界 EXCITE【AI增强】 中出しワールド EXCITE "
        "主演女優: 星優乃・浜崎ひめ スタジオ: ムゲン "
        + ("カテゴリで探す:完全無修正" * 8)
    )
    got = resolve_sub_filename(inner_name=jp, title="BD二部", hash_value="C" * 40)
    assert "主演女優" not in got
    assert "カテゴリ" not in got
    assert len(got) <= 200
    assert got.startswith("BD-M01")
