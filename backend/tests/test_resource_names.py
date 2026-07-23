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

    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)

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
        object(), parsed, source_url="https://x/thread-1-1-1.html"
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
        object(), parsed2, source_url="https://x/thread-2-1-1.html"
    )
    assert calls[0]["title"] == "单资源帖"
    # ed2k 链内名不是子资源名 → 退回主标题
    assert calls[0]["filename"] == "单资源帖"
