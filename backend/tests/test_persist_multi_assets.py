"""多磁力入库：按资源名称分组（同名多链合并，异名分行）。"""

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
                "size": int(getattr(link, "size", 0) or 0),
                "ed2k_links": kwargs.get("ed2k_links"),
                "preview_images": kwargs.get("preview_images"),
                "title": kwargs.get("title"),
                "import_outcome": kwargs.get("import_outcome"),
                "commit": kwargs.get("commit", True),
            }
        )
        return True

    monkeypatch.setattr(persist_mod, "upsert_resource", fake_upsert)
    return calls


class _FakeConn:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass


def test_different_names_upsert_each_resource(monkeypatch):
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
            filename="子文件C.mp4",
            size=20,
            uri="magnet:?xt=urn:btih:" + "C" * 40,
            is_primary=False,
        ),
    ]
    conn = _FakeConn()
    out = persist_mod.persist_dual_parse(
        conn,
        _parsed(*assets),
        source_url="https://example.com/thread-1-1-1.html",
        board_fid="36:668",
    )
    assert out["count"] == 3
    assert out["import_outcome"].startswith("成功：已提取 3 条资源")
    assert "形态:多资源" in out["import_outcome"]
    assert [c["filename"] for c in calls] == ["子文件A.mp4", "子文件B.mp4", "子文件C.mp4"]
    for c in calls:
        assert c["title"] == "合集帖"
        assert c["ed2k_links"] == [c["uri"]]
        assert c["commit"] is False
        assert str(c.get("import_outcome") or "").startswith("成功：已提取 3 条资源")
    assert conn.commits == 1


def test_truncated_name_merged_into_long_name(monkeypatch):
    calls = _patch_common(monkeypatch)
    long = "【磁力分享】【自整理】欧美系列1080P AuntJudys更新至23.05.28【2820V 1.11TB】 【磁力+目录】"
    short = "【磁力分享】【自整理】欧美系列1080P AuntJudys更新至23.05.28【2820V 1.1"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=long,
            size=0,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=short,
            size=0,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
        ),
    ]
    parsed = _parsed(*assets, title="帖")
    parsed.description = "【资源大小】：2820V 1.11TB"
    parsed.preview_images = ["https://example.com/p.jpg"]
    out = persist_mod.persist_dual_parse(
        _FakeConn(),
        parsed,
        source_url="https://example.com/thread-trunc-1-1.html",
    )
    assert out["count"] == 1
    assert len(calls) == 1
    # resolve_sub_filename 会折叠容量段空格（2820V 1.11TB → 2820V1.11TB）
    got = calls[0]["filename"] or ""
    assert "AuntJudys" in got and "2820V" in got and "1.11TB" in got
    assert len(calls[0]["ed2k_links"]) == 2
    assert calls[0]["preview_images"] == ["https://example.com/p.jpg"]
    assert calls[0]["size"] == int(1.11 * 1024**4)


def test_same_name_fills_size_and_thread_previews(monkeypatch):
    calls = _patch_common(monkeypatch)
    name = "合集包"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=name,
            size=0,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=name,
            size=0,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
        ),
    ]
    parsed = _parsed(*assets, title="帖【13V 66.7GB】")
    parsed.description = "【资源名称】：合集包\n【资源大小】：13V 66.7GB"
    parsed.preview_images = [
        "https://example.com/1.jpg",
        "https://example.com/2.jpg",
        "https://example.com/3.jpg",
        "https://example.com/4.jpg",
        "https://example.com/5.jpg",
        "https://example.com/6.jpg",
    ]
    out = persist_mod.persist_dual_parse(
        _FakeConn(),
        parsed,
        source_url="https://example.com/thread-size-1-1.html",
    )
    assert out["count"] == 1
    assert len(calls) == 1
    assert calls[0]["size"] == int(66.7 * 1024**3)
    assert calls[0]["preview_images"] == parsed.preview_images[:5]


def test_same_name_merges_links_into_one_resource(monkeypatch):
    calls = _patch_common(monkeypatch)
    name = "流川莉央合集包"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=name,
            size=100,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=name,
            size=50,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
            is_primary=False,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="C" * 40,
            filename=name,
            size=20,
            uri="magnet:?xt=urn:btih:" + "C" * 40,
            is_primary=False,
        ),
    ]
    out = persist_mod.persist_dual_parse(
        _FakeConn(),
        _parsed(*assets, title="帖标题"),
        source_url="https://example.com/thread-pack-1-1.html",
    )
    assert out["count"] == 1
    assert out["import_outcome"].startswith("成功：已提取主链")
    assert "形态:单资源" in out["import_outcome"]
    assert len(calls) == 1
    assert calls[0]["filename"] == name
    assert calls[0]["title"] == "帖标题"
    assert calls[0]["hash"] == "A" * 40
    assert calls[0]["ed2k_links"] == [
        "magnet:?xt=urn:btih:" + "A" * 40,
        "magnet:?xt=urn:btih:" + "B" * 40,
        "magnet:?xt=urn:btih:" + "C" * 40,
    ]


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
        _FakeConn(),
        _parsed(asset, title="【单资源】示例帖"),
        source_url="https://example.com/thread-2-1-1.html",
    )
    assert calls[0]["title"] == "【单资源】示例帖"
    assert calls[0]["filename"] == "专属片名.mp4"
    assert calls[0]["commit"] is False


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
        _FakeConn(),
        _parsed(asset, title="重爬帖"),
        source_url="https://www.sehuatang.net/thread-2663222-1-1.html",
        replace_thread_assets=True,
    )
    assert out["purged"] == 2
    assert len(purged) == 1
    assert purged[0][0].endswith("thread-2663222-1-1.html")
    assert purged[0][1] == {"E70B408068F72D258C054F299E9FFA15"}


def test_replace_same_name_keeps_only_primary_hash(monkeypatch):
    _patch_common(monkeypatch)
    purged: list[tuple] = []

    def fake_purge(conn, source_url, keep_hashes, **kwargs):
        purged.append((source_url, set(keep_hashes), kwargs.get("commit")))
        return 2

    monkeypatch.setattr(persist_mod, "delete_other_resources_by_source_url", fake_purge)
    name = "同一资源名"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=name,
            size=10,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=name,
            size=5,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
        ),
    ]
    out = persist_mod.persist_dual_parse(
        _FakeConn(),
        _parsed(*assets),
        source_url="https://example.com/thread-merge-1-1.html",
        replace_thread_assets=True,
    )
    assert out["count"] == 1
    assert out["purged"] == 2
    assert purged[0][1] == {"A" * 40}


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
        _FakeConn(),
        _parsed(asset),
        source_url="https://example.com/thread-3-1-1.html",
    )
    assert calls["n"] == 0


class _OccupancyConn:
    """cursor 查询 hash→source_url；无行视为空闲。兼容单查与 ANY 批量。"""

    def __init__(self, owners: dict[str, str]) -> None:
        self.owners = {k.upper(): v for k, v in owners.items()}
        self.commits = 0
        self.queries = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def cursor(self):
        owners = self.owners
        parent = self

        class _Cur:
            def __init__(self) -> None:
                self._row = None
                self._rows: list[tuple[str, str]] = []

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                parent.queries += 1
                arg0 = (params or ("",))[0]
                if isinstance(arg0, (list, tuple)):
                    self._rows = []
                    for raw in arg0:
                        key = str(raw or "").strip().upper()
                        if key in owners:
                            self._rows.append((key, owners[key]))
                    self._row = None
                    return
                h = str(arg0 or "").strip().upper()
                url = owners.get(h)
                self._row = (url,) if url is not None else None
                self._rows = []

            def fetchone(self):
                return self._row

            def fetchall(self):
                return list(self._rows)

        return _Cur()


def test_large_pack_pick_batches_not_per_hash(monkeypatch):
    """900+ 同名链：占用检查应批量查询，而非每 hash 一次。"""
    calls = _patch_common(monkeypatch)
    mine = "https://example.com/thread-pack-1-1.html"
    name = "大包名"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash=f"{i:040x}",
            filename=name,
            size=100 - (i % 7),
            uri=f"magnet:?xt=urn:btih:{i:040x}",
            is_primary=(i == 0),
        )
        for i in range(200)
    ]
    # 仅主链被其它帖占用 → 应选到空闲 hash，且查询次数远小于 200
    conn = _OccupancyConn({f"{0:040x}": "https://example.com/other.html"})
    out = persist_mod.persist_dual_parse(
        conn,
        _parsed(*assets, title="大包帖"),
        source_url=mine,
        replace_thread_assets=True,
    )
    assert out["count"] == 1
    assert calls[0]["filename"] == name
    assert len(calls[0]["ed2k_links"] or []) == 200
    assert conn.queries <= 5


def test_occupied_hashes_use_synthetic_row_key(monkeypatch):
    from db.repository import name_row_hash

    calls = _patch_common(monkeypatch)
    other = "https://example.com/thread-other-1-1.html"
    mine = "https://example.com/thread-mine-1-1.html"
    name = "合集资源名"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=name,
            size=100,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=name,
            size=50,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
        ),
    ]
    conn = _OccupancyConn({"A" * 40: other, "B" * 40: other})
    out = persist_mod.persist_dual_parse(
        conn,
        _parsed(*assets, title="新帖标题"),
        source_url=mine,
        replace_thread_assets=True,
    )
    syn = name_row_hash(mine, name)
    assert out["count"] == 1
    assert calls[0]["hash"] == syn
    assert calls[0]["ed2k_links"] == [
        "magnet:?xt=urn:btih:" + "A" * 40,
        "magnet:?xt=urn:btih:" + "B" * 40,
    ]
    assert calls[0]["filename"] == name


def test_replace_keeps_writable_not_group_primary(monkeypatch):
    from db.repository import name_row_hash

    _patch_common(monkeypatch)
    purged: list[set[str]] = []

    def fake_purge(conn, source_url, keep_hashes, **kwargs):
        purged.append(set(keep_hashes))
        return 1

    monkeypatch.setattr(persist_mod, "delete_other_resources_by_source_url", fake_purge)
    other = "https://example.com/thread-other-1-1.html"
    mine = "https://example.com/thread-mine2-1-1.html"
    name = "包名"
    assets = [
        ParsedAsset(
            link_kind="magnet",
            hash="A" * 40,
            filename=name,
            size=100,
            uri="magnet:?xt=urn:btih:" + "A" * 40,
            is_primary=True,
        ),
        ParsedAsset(
            link_kind="magnet",
            hash="B" * 40,
            filename=name,
            size=10,
            uri="magnet:?xt=urn:btih:" + "B" * 40,
        ),
    ]
    # A 被占，B 空闲 → 应写 B 并 keep B（不是分组主链 A）
    conn = _OccupancyConn({"A" * 40: other})
    out = persist_mod.persist_dual_parse(
        conn,
        _parsed(*assets),
        source_url=mine,
        replace_thread_assets=True,
    )
    assert out["count"] == 1
    assert purged[0] == {"B" * 40}
    assert name_row_hash(mine, name) not in purged[0]
