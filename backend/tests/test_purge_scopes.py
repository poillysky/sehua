"""Split purge: crawl-only vs resources-only."""

from db.repository import purge_crawl_data, purge_resources


def test_purge_resources_respects_reset_crawl_flag():
    deleted: list[str] = []

    class FakeCur:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, sql, params=None):
            s = " ".join(str(sql).split())
            if "to_regclass" in s:
                self._name = params[0].split(".")[-1]
                return
            if s.startswith("DELETE FROM"):
                deleted.append(s.split()[-1])

        def fetchone(self):
            return (f"public.{getattr(self, '_name', '')}",)

    class FakeConn:
        def cursor(self):
            return FakeCur()

        def commit(self):
            pass

    purge_resources(FakeConn(), reset_crawl=False)
    assert "ed2k_resources" in deleted
    assert "crawl_pages" not in deleted

    deleted.clear()
    purge_resources(FakeConn(), reset_crawl=True)
    assert "ed2k_resources" in deleted
    assert "crawl_pages" in deleted


def test_purge_crawl_data_skips_resources():
    deleted: list[str] = []

    class FakeCur:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def execute(self, sql, params=None):
            s = " ".join(str(sql).split())
            if "to_regclass" in s:
                self._name = params[0].split(".")[-1]
                return
            if s.startswith("DELETE FROM"):
                deleted.append(s.split()[-1])

        def fetchone(self):
            return (f"public.{getattr(self, '_name', '')}",)

    class FakeConn:
        def cursor(self):
            return FakeCur()

        def commit(self):
            pass

    purge_crawl_data(FakeConn())
    assert "crawl_pages" in deleted
    assert "crawl_activity_log" in deleted
    assert "ed2k_resources" not in deleted
