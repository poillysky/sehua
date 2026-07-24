"""Sliding-window imports_per_minute."""

from __future__ import annotations

import time

from workers.import_rate import (
    import_rate_snapshot,
    imports_per_minute,
    note_persisted,
    reset_import_rate_for_tests,
)


def test_imports_per_minute_counts_window() -> None:
    reset_import_rate_for_tests()
    assert imports_per_minute() == 0
    for _ in range(5):
        note_persisted(kind="import")
    assert imports_per_minute() == 5
    snap = import_rate_snapshot()
    assert snap["per_minute"] == 5
    assert snap["window_sec"] == 60


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
    assert imports_per_minute() == 1
