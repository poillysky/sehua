"""多磁力逐条入库 + filename 命名规则。"""

from __future__ import annotations

from parsers.links import DualParseResult, ParsedAsset
from db import persist as persist_mod


def _parsed(*assets: ParsedAsset, title: str = "合集帖") -> DualParseResult:
    return DualParseResult(
        tid=1,
        title=title,
        description="desc",
        metadata={},
        preview_images=[],
        extract_password="",
        magnets=[],
        ed2k_links=[],
        assets=list(assets),
        primary_link_kind=assets[0].link_kind if assets else "none",
    )


def _patch_common(monkeypatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)
    monkeypatch.setattr(persist_mod, "delete_stub_by_source_url", lambda *a, **k: False)
    monkeypatch.setattr(persist_mod, "sync_board_meta_by_source_url", lambda *a, **k: 0)
    monkeypatch.setattr(persist_mod, "delete_other_resources_by_source_url", lambda *a, **k: 0)

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append(
            {
                "hash": link.hash,
                "filename": link.filename,
                "uri": link.link,
                "ed2k_links": kwargs.get("ed2k_links"),
                "title": kwargs.get("title"),
            }
        )
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)
    return calls


def test_multi_magnet_upserts_each_as_single_resource(monkeypatch):
    calls = _patch_common(monkeypatch)

    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename="子文件A.mp4",
            size=100,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename="子文件B.mp4",
            size=50,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
            is_primary=False,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="C" * 40,
            filename="magnet-CCCCCCCC",
            size=20,
            uri="magnet:?xt=urn:btih:" + "C" * 40,
            is_primary=False,
        ),
    ]
    out = persist_mod.persist_dual_parse(
        object(),
        _parsed(*assets),
        source_url="https://example.com/thread-1-1-1.html",
        board_fid="36:668",
    )
    assert out["count"] == 3
    assert [c["filename"] for c in calls] == ["子文件A.mp4", "子文件B.mp4", "合集帖"]
    for c in calls:
        assert c["title"] == "合集帖"
        assert c["ed2k_links"] == [c["uri"]]


def test_single_keeps_real_filename(monkeypatch):
    calls = _patch_common(monkeypatch)

    asset = ParsedAsset(
        link_kind="magnet",
        hash="D" * 40,
        filename="专属片名.mp4",
        size=1,
        uri="magnet:?xt=urn:btih:" + "D" * 40 + "&dn=alone.mp4",
        is_primary=True,
    )
    persist_mod.persist_dual_parse(
        object(),
        _parsed(asset, title="【单资源】示例帖"),
        source_url="https://example.com/thread-2-1-1.html",
    )
    assert calls[0]["title"] == "【单资源】示例帖"
    assert calls[0]["filename"] == "专属片名.mp4"


def test_replace_thread_assets_purges_old_hashes(monkeypatch):
    _patch_common(monkeypatch)
    purged: list[tuple] = []

    def fake_purge(conn, source_url, keep_hashes, **kwargs):
        purged.append((source_url, set(keep_hashes), kwargs.get("commit")))
        return 2

    monkeypatch.setattr(persist_mod, "delete_other_resources_by_source_url", fake_purge)

    asset = ParsedAsset(
        link_kind="ed2k",
        hash="E70B408068F72D258C054F299E9FFA15",
        filename="new.mp4",
        size=10,
        uri="ed2k://|file|new.mp4|10|E70B408068F72D258C054F299E9FFA15|/",
        is_primary=True,
    )
    out = persist_mod.persist_dual_parse(
        object(),
        _parsed(asset, title="重爬帖"),
        source_url="https://www.sehuatang.net/thread-2663222-1-1.html",
        replace_thread_assets=True,
    )
    assert out["purged"] == 2
    assert len(purged) == 1
    assert purged[0][0].endswith("thread-2663222-1-1.html")
    assert purged[0][1] == {"E70B408068F72D258C054F299E9FFA15"}


def test_replace_thread_assets_off_by_default(monkeypatch):
    _patch_common(monkeypatch)
    calls = {"n": 0}

    def fake_purge(*a, **k):
        calls["n"] += 1
        return 0

    monkeypatch.setattr(persist_mod, "delete_other_resources_by_source_url", fake_purge)
    asset = ParsedAsset(
        link_kind="magnet",
        hash="F" * 40,
        filename="a.mp4",
        size=1,
        uri="magnet:?xt=urn:btih:" + "F" * 40,
        is_primary=True,
    )
    persist_mod.persist_dual_parse(
        object(),
        _parsed(asset),
        source_url="https://example.com/thread-3-1-1.html",
    )
    assert calls["n"] == 0
