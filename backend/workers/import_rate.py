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


def imports_per_minute() -> int:
    """How many threads were persisted in the last 60 seconds."""
    now = time.monotonic()
    with _lock:
        _prune(now)
        return len(_times)


def import_rate_snapshot() -> dict[str, int | float]:
    return {
        "per_minute": imports_per_minute(),
        "window_sec": int(_WINDOW_SEC),
    }


def reset_import_rate_for_tests() -> None:
    with _lock:
        _times.clear()
