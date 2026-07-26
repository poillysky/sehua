"""Sliding-window crawl persist rate (posts/min) for crawler UI."""

from __future__ import annotations

import threading
import time
from collections import deque

_WINDOW_SEC = 60.0
_lock = threading.Lock()
_times: deque[float] = deque()


def _prune(now: float) -> None:
    cutoff = now - _WINDOW_SEC
    while _times and _times[0] < cutoff:
        _times.popleft()


def note_persisted(*, kind: str = "import") -> None:
    """Record one thread written to the resource DB (import or stub)."""
    del kind  # reserved for future breakdown
    now = time.monotonic()
    with _lock:
        _times.append(now)
        _prune(now)


def _rate_from_times(now: float) -> tuple[int, int]:
    """Return (per_minute extrapolated, raw count in window)."""
    _prune(now)
    n = len(_times)
    if n <= 0:
        return 0, 0
    span = max(3.0, now - _times[0])
    span = min(span, _WINDOW_SEC)
    return int(round(n * 60.0 / span)), n


def imports_per_minute() -> int:
    """Estimated posts/min from in-process notes (fallback)."""
    now = time.monotonic()
    with _lock:
        rate, _ = _rate_from_times(now)
        return rate


def import_rate_snapshot() -> dict[str, int | float]:
    """Prefer activity-log rate (matches 活动日志); fall back to memory notes."""
    try:
        from db.activity import persisted_rate_from_log

        snap = persisted_rate_from_log(int(_WINDOW_SEC))
        if snap is not None:
            return {
                "per_minute": int(snap.get("per_minute") or 0),
                "window_sec": int(snap.get("window_sec") or _WINDOW_SEC),
                "raw_count": int(snap.get("raw_count") or 0),
            }
    except Exception:
        pass
    now = time.monotonic()
    with _lock:
        rate, raw = _rate_from_times(now)
        return {
            "per_minute": rate,
            "window_sec": int(_WINDOW_SEC),
            "raw_count": raw,
        }


def reset_import_rate_for_tests() -> None:
    with _lock:
        _times.clear()
