"""备份导入：解析 gzip/zip SQL，按 hash / 标签名去重合并。"""

from __future__ import annotations

import gzip
import io
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from workers import backup_import as bi


def _python_fallback_sql() -> str:
    return """
-- sehuatang resource backup (python fallback)
BEGIN;
DELETE FROM import_jobs;
DELETE FROM resource_tags;
DELETE FROM resource_sources;
DELETE FROM ed2k_resources;
DELETE FROM tags;
INSERT INTO tags (id, name) VALUES (10, '有码');
INSERT INTO tags (id, name) VALUES (11, '高清');
INSERT INTO ed2k_resources (hash, filename, size, ed2k_link, extension, search_string, tsv, created_at, updated_at) VALUES ('AAAABBBBCCCCDDDDEEEEFFFF00001111', 'demo.mp4', 12345, 'ed2k://|file|demo.mp4|12345|AAAABBBBCCCCDDDDEEEEFFFF00001111|/', 'mp4', 'demo.mp4', NULL, '2024-01-01 00:00:00+00', '2024-01-01 00:00:00+00');
INSERT INTO resource_sources (id, hash, source_id, source_url, title, description, preview_images, ed2k_links, extract_password, board_fid, board_name, forum_id, import_outcome) VALUES (1, 'AAAABBBBCCCCDDDDEEEEFFFF00001111', 2, 'https://example.com/t/1', '标题A', '描述A', '{"https://img/1.jpg"}', '{"ed2k://|file|demo.mp4|12345|AAAABBBBCCCCDDDDEEEEFFFF00001111|/"}', 'pass', '95', '板块', 'sehuatang', 'ok');
INSERT INTO resource_tags (hash, tag_id) VALUES ('AAAABBBBCCCCDDDDEEEEFFFF00001111', 10);
INSERT INTO resource_tags (hash, tag_id) VALUES ('AAAABBBBCCCCDDDDEEEEFFFF00001111', 11);
COMMIT;
"""


def _copy_sql() -> str:
    return """
--
-- PostgreSQL database dump
--
COPY public.tags (id, name) FROM stdin;
10	有码
11	高清
\\.
COPY public.ed2k_resources (hash, filename, size, ed2k_link, search_string) FROM stdin;
AAAABBBBCCCCDDDDEEEEFFFF00001111	demo.mp4	12345	ed2k://|file|demo.mp4|12345|AAAABBBBCCCCDDDDEEEEFFFF00001111|/	demo.mp4
\\.
COPY public.resource_sources (hash, source_id, source_url, title) FROM stdin;
AAAABBBBCCCCDDDDEEEEFFFF00001111	2	https://example.com/t/1	标题A
\\.
COPY public.resource_tags (hash, tag_id) FROM stdin;
AAAABBBBCCCCDDDDEEEEFFFF00001111	10
\\.
"""


def test_extract_sql_from_gzip():
    raw = gzip.compress(_python_fallback_sql().encode("utf-8"))
    text = bi.extract_sql_text(raw, "ed2k-resources.sql.gz")
    assert "INSERT INTO ed2k_resources" in text


def test_extract_sql_from_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "ed2k-resources.sql.gz",
            gzip.compress(_python_fallback_sql().encode("utf-8")),
        )
    text = bi.extract_sql_text(buf.getvalue(), "backup.zip")
    assert "demo.mp4" in text


def test_parse_python_fallback_skips_delete_and_generated():
    tables = bi.parse_backup_tables(_python_fallback_sql())
    assert "import_jobs" not in tables
    assert len(tables["tags"]) == 2
    assert len(tables["ed2k_resources"]) == 1
    row = tables["ed2k_resources"][0]
    assert row["hash"] == "AAAABBBBCCCCDDDDEEEEFFFF00001111"
    assert "extension" not in row
    assert "tsv" not in row
    assert row["filename"] == "demo.mp4"
    src = tables["resource_sources"][0]
    assert src["title"] == "标题A"
    assert src["preview_images"] == ["https://img/1.jpg"]
    assert len(tables["resource_tags"]) == 2


def test_parse_copy_format():
    tables = bi.parse_backup_tables(_copy_sql())
    assert tables["tags"][0]["name"] == "有码"
    assert tables["ed2k_resources"][0]["size"] == 12345
    assert tables["resource_sources"][0]["source_url"] == "https://example.com/t/1"


def test_apply_backup_dedup_by_hash(monkeypatch):
    """同一 hash 第二次导入记为 update；标签按 name 映射。"""
    calls: list[str] = []
    tag_ids = {"有码": 100, "高清": 101}
    existing: set[str] = set()

    class _Cur:
        def __init__(self):
            self.rowcount = 0
            self._last = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            sql_l = " ".join(sql.split()).lower()
            self._last = (sql_l, params)
            self.rowcount = 0
            if "from sources where id" in sql_l:
                self._fetch = (2,) if params and params[0] == 2 else None
            elif "insert into tags" in sql_l:
                self._fetch = None
            elif "select id from tags where name" in sql_l:
                self._fetch = (tag_ids[params[0]],)
            elif "from ed2k_resources where hash" in sql_l:
                h = params[0]
                if h in existing:
                    self._fetch = ("demo.mp4", 12345, "ed2k://|file|demo.mp4|12345|" + h + "|/")
                else:
                    self._fetch = None
            elif "insert into resource_tags" in sql_l:
                self.rowcount = 1
                self._fetch = None
            else:
                self._fetch = None

        def fetchone(self):
            return self._fetch

    class _Conn:
        def cursor(self):
            return _Cur()

        def commit(self):
            return None

        def close(self):
            return None

    def fake_ensure(conn, key, name, source_type, url=None):
        return 2

    def fake_upsert(conn, link, source_id, **kwargs):
        calls.append(link.hash)
        existing.add(link.hash)
        return True

    monkeypatch.setattr(bi, "ensure_source", fake_ensure)
    monkeypatch.setattr(bi, "upsert_resource", fake_upsert)

    tables = bi.parse_backup_tables(_python_fallback_sql())
    conn = _Conn()
    s1 = bi.apply_backup_tables(conn, tables)
    assert s1["resources_inserted"] == 1
    assert s1["resources_updated"] == 0
    assert s1["tags_upserted"] == 2
    assert s1["resource_tags_linked"] == 2

    s2 = bi.apply_backup_tables(conn, tables)
    assert s2["resources_inserted"] == 0
    assert s2["resources_updated"] == 1
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_run_backup_import_uses_shared_lock(monkeypatch):
    from workers import backup as bk

    if bk._LOCK.locked():
        bk._LOCK.release()
    bk._BUSY = False

    monkeypatch.setattr(bi, "extract_sql_text", lambda raw, filename="": _python_fallback_sql())
    monkeypatch.setattr(
        bi,
        "parse_backup_tables",
        lambda sql: {
            "ed2k_resources": [
                {
                    "hash": "AAAABBBBCCCCDDDDEEEEFFFF00001111",
                    "filename": "demo.mp4",
                    "size": 1,
                    "ed2k_link": "ed2k://|file|demo.mp4|1|AAAABBBBCCCCDDDDEEEEFFFF00001111|/",
                }
            ]
        },
    )
    monkeypatch.setattr(
        bi,
        "apply_backup_tables",
        lambda conn, tables: {
            "resources_inserted": 1,
            "resources_updated": 0,
            "resources_skipped": 0,
            "tags_upserted": 0,
            "resource_tags_linked": 0,
            "tables_seen": ["ed2k_resources"],
        },
    )
    monkeypatch.setattr(bi, "connect", lambda: MagicMock(close=lambda: None))
    monkeypatch.setattr(bk, "_crawler_snapshot", lambda: {"was_enabled": False})
    monkeypatch.setattr(bk, "_pause_crawler", AsyncMock())
    monkeypatch.setattr(bk, "_resume_crawler", AsyncMock())

    result = await bi.run_backup_import(raw=b"x", filename="t.sql.gz")
    assert result["ok"] is True
    assert result["resources_inserted"] == 1
    assert bk._BUSY is False
    assert not bk._LOCK.locked()
