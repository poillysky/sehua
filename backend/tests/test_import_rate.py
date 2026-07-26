"""Sliding-window imports_per_minute."""

from __future__ import annotations

import time

from workers.import_rate import (
    import_rate_snapshot,
    imports_per_minute,
    note_persisted,
    reset_import_rate_for_tests,
)


def test_imports_per_minute_extrapolates_burst(monkeypatch) -> None:
    reset_import_rate_for_tests()
    assert imports_per_minute() == 0
    base = 1_000_000.0
    clock = {"t": base}

    def fake_mono() -> float:
        return clock["t"]

    monkeypatch.setattr(time, "monotonic", fake_mono)
    for i in range(5):
        clock["t"] = base + i
        note_persisted(kind="import")
    # 5 帖 · span=4s → 5*60/4 = 75
    clock["t"] = base + 4
    assert imports_per_minute() == 75


def test_imports_per_minute_full_window(monkeypatch) -> None:
    reset_import_rate_for_tests()
    base = 2_000_000.0
    clock = {"t": base}

    def fake_mono() -> float:
        return clock["t"]

    monkeypatch.setattr(time, "monotonic", fake_mono)
    for i in range(9):
        clock["t"] = base + i * 6
        note_persisted()
    clock["t"] = base + 54
    # span≈54 → 9*60/54 = 10
    assert imports_per_minute() == 10


def test_imports_per_minute_prunes_old(monkeypatch) -> None:
    reset_import_rate_for_tests()
    base = 1_000_000.0
    clock = {"t": base}

    def fake_mono() -> float:
        return clock["t"]

    monkeypatch.setattr(time, "monotonic", fake_mono)
    note_persisted()
    clock["t"] = base + 61
    assert imports_per_minute() == 0
    note_persisted()
    # 单点 span 下限 3s → 1*60/3 = 20
    assert imports_per_minute() == 20


def test_import_rate_snapshot_prefers_activity_log(monkeypatch) -> None:
    reset_import_rate_for_tests()
    monkeypatch.setattr(
        "db.activity.persisted_rate_from_log",
        lambda _w=60: {"per_minute": 57, "window_sec": 60, "raw_count": 18},
    )
    snap = import_rate_snapshot()
    assert snap["per_minute"] == 57
    assert snap["raw_count"] == 18


def test_import_rate_snapshot_falls_back_memory(monkeypatch) -> None:
    reset_import_rate_for_tests()
    monkeypatch.setattr("db.activity.persisted_rate_from_log", lambda _w=60: None)
    note_persisted()
    snap = import_rate_snapshot()
    assert snap["window_sec"] == 60
    assert int(snap["per_minute"]) >= 1
    assert int(snap.get("raw_count") or 0) >= 1
