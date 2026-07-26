# -*- coding: utf-8 -*-
"""配置 Cookie 保存时同步本地 jar：清空即游客，填入即生效。"""

from __future__ import annotations

import json
from pathlib import Path

from workers.session_factory import (
    cookie_header_to_map,
    session_from_config,
    sync_forum_cookie_jars,
    write_cookie_jar,
)


def test_cookie_header_to_map():
    got = cookie_header_to_map("a=1; b=two; ; bad; c=")
    assert got == {"a": "1", "b": "two"}


def test_sync_clears_and_writes_jars(tmp_path, monkeypatch):
    from crawler.sites import forum_2048 as f2048
    from workers import session_factory as sf

    jar = tmp_path / "cookies_2048.json"
    acc = tmp_path / "cookies_account_2048.json"
    monkeypatch.setattr(f2048, "COOKIE_FILE_2048", jar)
    monkeypatch.setattr(sf, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(sf, "ACCOUNT_COOKIE_FILE", tmp_path / "cookies_account.json")

    # 先写入脏登录态
    write_cookie_jar(jar, {"safe": "1", "a22e7_winduser": "OLD"})
    write_cookie_jar(acc, {"safe": "1", "a22e7_winduser": "OLDACC"})

    sync_forum_cookie_jars(
        "2048",
        {"web_crawler_cookie": "", "web_crawler_account_cookie": ""},
    )
    assert json.loads(jar.read_text(encoding="utf-8")) == {"safe": "1"}
    assert json.loads(acc.read_text(encoding="utf-8")) == {"safe": "1"}

    sync_forum_cookie_jars(
        "2048",
        {
            "web_crawler_cookie": "safe=1; a22e7_winduser=NEW",
            "web_crawler_account_cookie": "a22e7_winduser=ACC",
        },
    )
    normal = json.loads(jar.read_text(encoding="utf-8"))
    assert normal["a22e7_winduser"] == "NEW"
    account = json.loads(acc.read_text(encoding="utf-8"))
    assert account["a22e7_winduser"] == "ACC"


def test_session_from_config_empty_ignores_stale_jar(tmp_path, monkeypatch):
    from crawler.sites import forum_2048 as f2048

    jar = tmp_path / "cookies_2048.json"
    monkeypatch.setattr(f2048, "COOKIE_FILE_2048", jar)
    write_cookie_jar(jar, {"safe": "1", "a22e7_winduser": "STALE"})

    session = session_from_config(
        {"web_crawler_cookie": "", "web_crawler_ua": "UA"},
        forum_id="2048",
    )
    assert session.cookies.get("a22e7_winduser") is None
    assert session.cookies.get("safe") == "1"

    session2 = session_from_config(
        {"web_crawler_cookie": "a22e7_winduser=LIVE; foo=bar", "web_crawler_ua": "UA"},
        forum_id="2048",
    )
    assert session2.cookies.get("a22e7_winduser") == "LIVE"
    assert session2.cookies.get("foo") == "bar"


def test_guest_bootstrap_does_not_revive_jar_login(tmp_path, monkeypatch):
    """普通 Cookie 未填时，进站前不得从 jar 复活登录态。"""
    from crawler.sites import forum_2048 as f2048

    jar = tmp_path / "cookies_2048.json"
    monkeypatch.setattr(f2048, "COOKIE_FILE_2048", jar)
    write_cookie_jar(jar, {"safe": "1", "a22e7_winduser": "STALE_ACC"})

    session = session_from_config(
        {"web_crawler_cookie": "", "web_crawler_ua": "UA"},
        forum_id="2048",
    )
    session.apply_config_cookie_authority()
    assert session.cookies.get("a22e7_winduser") is None
    assert session.cookies == {"safe": "1"}

    # 填了登录 Cookie 时仍可与 jar 合并，且配置键覆盖
    write_cookie_jar(jar, {"safe": "1", "a22e7_winduser": "JAR", "extra": "1"})
    session2 = session_from_config(
        {"web_crawler_cookie": "a22e7_winduser=CFG", "web_crawler_ua": "UA"},
        forum_id="2048",
    )
    session2.apply_config_cookie_authority()
    assert session2.cookies.get("a22e7_winduser") == "CFG"
    assert session2.cookies.get("extra") == "1"


def test_account_jar_uses_account_cookie_not_normal(tmp_path, monkeypatch):
    """账号爬 jar：未显式 override 时读账号 Cookie，不误用普通 Cookie。"""
    from crawler.sites import forum_2048 as f2048
    from workers import session_factory as sf

    jar = tmp_path / "cookies_2048.json"
    acc = tmp_path / "cookies_account_2048.json"
    monkeypatch.setattr(f2048, "COOKIE_FILE_2048", jar)
    monkeypatch.setattr(sf, "_DATA_DIR", tmp_path)
    write_cookie_jar(jar, {"safe": "1", "a22e7_winduser": "NORMAL"})
    write_cookie_jar(acc, {"safe": "1", "a22e7_winduser": "OLDACC"})

    session = session_from_config(
        {
            "web_crawler_cookie": "a22e7_winduser=NORMAL_CFG",
            "web_crawler_account_cookie": "a22e7_winduser=ACC_CFG",
            "web_crawler_ua": "UA",
        },
        forum_id="2048",
        account_jar=True,
    )
    assert session.cookie_file == acc
    assert session.cookies.get("a22e7_winduser") == "ACC_CFG"

    guest_acc = session_from_config(
        {
            "web_crawler_cookie": "a22e7_winduser=NORMAL_CFG",
            "web_crawler_account_cookie": "",
            "web_crawler_ua": "UA",
        },
        forum_id="2048",
        account_jar=True,
    )
    assert guest_acc.cookies.get("a22e7_winduser") is None
    assert guest_acc.cookies.get("safe") == "1"
