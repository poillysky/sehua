"""Persistent state for one-post-at-a-time parse evolution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / "data" / "parse_evolution_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_STATE
    if not p.exists():
        return {
            "version": 1,
            "forum_id": "2048",
            "active_bucket": None,
            "updated_at": None,
            "posts": {},  # tid -> record
            "buckets": {},  # name -> {passed, failed, pending counts cached}
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(state: dict[str, Any], path: Path | None = None) -> Path:
    p = path or DEFAULT_STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def upsert_post(state: dict[str, Any], record: dict[str, Any]) -> None:
    tid = str(record.get("tid") or "")
    if not tid:
        raise ValueError("record needs tid")
    prev = state.setdefault("posts", {}).get(tid) or {}
    merged = {**prev, **record, "updated_at": _now()}
    state["posts"][tid] = merged


def recompute_buckets(state: dict[str, Any]) -> dict[str, dict[str, int]]:
    buckets: dict[str, dict[str, int]] = {}
    for rec in (state.get("posts") or {}).values():
        b = rec.get("bucket") or "?"
        st = rec.get("status") or "pending"
        slot = buckets.setdefault(
            b, {"pending": 0, "failed": 0, "passed": 0, "skipped": 0, "total": 0}
        )
        slot["total"] += 1
        if st == "passed":
            slot["passed"] += 1
        elif st == "failed":
            slot["failed"] += 1
        elif st == "skipped":
            slot["skipped"] += 1
        else:
            slot["pending"] += 1
    state["buckets"] = buckets
    return buckets


def next_in_bucket(state: dict[str, Any], bucket: str) -> dict[str, Any] | None:
    """Prefer failed (need re-verify after fix), then pending; skip passed/skipped."""
    posts = list((state.get("posts") or {}).values())
    failed = [
        p
        for p in posts
        if p.get("bucket") == bucket and p.get("status") == "failed"
    ]
    pending = [
        p
        for p in posts
        if p.get("bucket") == bucket
        and p.get("status") not in ("passed", "failed", "skipped")
    ]
    failed.sort(key=lambda x: int(x.get("tid") or 0))
    pending.sort(key=lambda x: int(x.get("tid") or 0))
    if failed:
        return failed[0]
    if pending:
        return pending[0]
    return None
