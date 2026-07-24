"""JWT secret must survive process restart when persisted to data dir."""

from __future__ import annotations

import auth.config as cfg


def test_jwt_secret_persists_to_data_file(tmp_path, monkeypatch) -> None:
    secret_file = tmp_path / "jwt_secret"
    monkeypatch.setattr(cfg, "_JWT_SECRET_FILE", secret_file)
    monkeypatch.setattr(cfg, "_cached_jwt_secret", None)
    monkeypatch.delenv("JWT_SECRET", raising=False)

    first = cfg.jwt_secret()
    assert first
    assert secret_file.is_file()
    assert secret_file.read_text(encoding="utf-8").strip() == first

    monkeypatch.setattr(cfg, "_cached_jwt_secret", None)
    second = cfg.jwt_secret()
    assert second == first


def test_jwt_secret_env_overrides_file(tmp_path, monkeypatch) -> None:
    secret_file = tmp_path / "jwt_secret"
    secret_file.write_text("from-disk-secret-value", encoding="utf-8")
    monkeypatch.setattr(cfg, "_JWT_SECRET_FILE", secret_file)
    monkeypatch.setattr(cfg, "_cached_jwt_secret", None)
    monkeypatch.setenv("JWT_SECRET", "from-env-secret-value")

    assert cfg.jwt_secret() == "from-env-secret-value"
