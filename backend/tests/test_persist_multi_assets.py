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


def test_multi_magnet_upserts_each_as_single_resource(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)

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
    calls: list[dict] = []
    monkeypatch.setattr(persist_mod, "ensure_source", lambda *a, **k: 1)

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append({"filename": link.filename, "title": kwargs.get("title")})
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)

    asset = ParsedAsset(
        link_kind="magnet",
        hash="D" * 40,
        filename="alone.mp4",
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
    assert calls[0]["filename"] == "alone.mp4"
