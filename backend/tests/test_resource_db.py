"""独立资源库连接：未启用时回落主库。"""

from __future__ import annotations

from db import resource_db as rdb


def test_resource_dsn_falls_back_to_primary(monkeypatch):
    primary = {
        "host": "primary-host",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
        "dbname": "ed2k",
    }
    monkeypatch.setattr(rdb, "primary_dsn_kwargs", lambda: dict(primary))
    monkeypatch.setattr(
        rdb,
        "_load_raw_from_primary",
        lambda: {
            "enabled": "false",
            "host": "",
            "port": "",
            "user": "",
            "password": "",
            "dbname": "",
        },
    )
    rdb.invalidate_resource_db_cache()
    assert rdb.resource_dsn_kwargs() == primary
    assert rdb.using_separate_resource_db() is False


def test_resource_dsn_uses_separate_when_enabled(monkeypatch):
    primary = {
        "host": "primary-host",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
        "dbname": "ed2k",
    }
    monkeypatch.setattr(rdb, "primary_dsn_kwargs", lambda: dict(primary))
    monkeypatch.setattr(
        rdb,
        "_load_raw_from_primary",
        lambda: {
            "enabled": "true",
            "host": "res-host",
            "port": "5433",
            "user": "res_user",
            "password": "res_pw",
            "dbname": "resources",
        },
    )
    rdb.invalidate_resource_db_cache()
    assert rdb.resource_dsn_kwargs() == {
        "host": "res-host",
        "port": 5433,
        "user": "res_user",
        "password": "res_pw",
        "dbname": "resources",
    }
    assert rdb.using_separate_resource_db() is True


def test_resource_dsn_inherits_primary_password_when_blank(monkeypatch):
    primary = {
        "host": "primary-host",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
        "dbname": "ed2k",
    }
    monkeypatch.setattr(rdb, "primary_dsn_kwargs", lambda: dict(primary))
    monkeypatch.setattr(
        rdb,
        "_load_raw_from_primary",
        lambda: {
            "enabled": "true",
            "host": "127.0.0.1",
            "port": "5432",
            "user": "",
            "password": "",
            "dbname": "ed2k_resources",
        },
    )
    rdb.invalidate_resource_db_cache()
    kwargs = rdb.resource_dsn_kwargs()
    assert kwargs["dbname"] == "ed2k_resources"
    assert kwargs["user"] == "postgres"
    assert kwargs["password"] == "secret"
