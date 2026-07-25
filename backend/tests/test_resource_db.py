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
    kwargs = rdb.resource_dsn_kwargs()
    assert kwargs["host"] == "res-host"
    assert kwargs["port"] == 5433
    assert kwargs["user"] == "res_user"
    assert kwargs["password"] == "res_pw"
    assert kwargs["dbname"] == "resources"
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


def test_connect_resource_fail_closed_when_separate_unreachable(monkeypatch):
    """启用独立库时连不上必须抛错，禁止静默回落主库。"""
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
            "host": "res-down",
            "port": "5433",
            "user": "res",
            "password": "pw",
            "dbname": "resources",
        },
    )
    rdb.invalidate_resource_db_cache()
    assert rdb.using_separate_resource_db() is True

    def boom(**_kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("psycopg2.connect", boom)
    try:
        rdb.connect_resource()
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        msg = str(exc)
        assert "写错库" in msg or "独立资源库" in msg
        assert "res-down" in msg or "数据管理" in msg
    finally:
        rdb.invalidate_resource_db_cache()


def test_settings_unavailable_fail_closed(monkeypatch):
    """主库设置读失败时禁止假装未启用而写主库。"""
    primary = {
        "host": "primary-host",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
        "dbname": "ed2k",
    }
    monkeypatch.setattr(rdb, "primary_dsn_kwargs", lambda: dict(primary))
    monkeypatch.setattr(rdb, "_env_resource_override", lambda: None)

    def boom_load():
        rdb._SETTINGS_UNAVAILABLE = True
        rdb._LAST_SETTINGS_ERROR = "multixact broken"
        return {
            "enabled": "false",
            "host": "",
            "port": "",
            "user": "",
            "password": "",
            "dbname": "",
        }

    monkeypatch.setattr(rdb, "_load_raw_from_primary", boom_load)
    rdb._CACHED_KWARGS = None
    rdb._CACHED_ENABLED = None
    assert rdb.using_separate_resource_db() is True
    try:
        rdb.resource_dsn_kwargs()
        assert False, "expected ResourceDbConfigError"
    except rdb.ResourceDbConfigError as exc:
        assert "写进" in str(exc) or "RESOURCE_DB" in str(exc)
    cfg = rdb.resource_db_config()
    assert cfg.get("settings_unavailable") is True
    assert cfg.get("writable") is False
    rdb.invalidate_resource_db_cache()


def test_forum_capabilities_and_focus_payload_helpers():
    from db.forum_configs import (
        FORUM_2048_ID,
        SITE_CRAWLER_FORUM_ID,
        forum_capabilities,
        list_crawlable_forum_ids,
    )

    caps = forum_capabilities(SITE_CRAWLER_FORUM_ID)
    assert caps["crawlable"] is True
    assert caps["registered"] is True
    caps2048 = forum_capabilities(FORUM_2048_ID)
    assert caps2048["crawlable"] is True
    ids = list_crawlable_forum_ids()
    assert SITE_CRAWLER_FORUM_ID in ids
    assert FORUM_2048_ID in ids
    assert forum_capabilities("unknown")["crawlable"] is False

