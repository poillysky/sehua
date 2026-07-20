"""Discuz 列表页发帖时间解析与最小龄期过滤。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta


def parse_discuz_list_datetime(raw: str, *, now: datetime | None = None) -> datetime | None:
    """解析列表日期：YYYY-MM-DD、刚刚/N分钟前、今天/昨天/前天 [+ HH:MM]。"""
    text = (raw or "").strip().replace("\xa0", " ")
    if not text:
        return None

    ref = now or datetime.now()
    if ref.tzinfo is not None:
        ref = ref.replace(tzinfo=None)

    absolute = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if absolute:
        try:
            return datetime(int(absolute.group(1)), int(absolute.group(2)), int(absolute.group(3)))
        except ValueError:
            return None

    if "分钟前" in text or "秒前" in text or "刚刚" in text:
        return ref
    if "小时前" in text:
        m = re.search(r"(\d+)\s*小时前", text)
        hours = int(m.group(1)) if m else 1
        return ref - timedelta(hours=max(1, hours))

    day_offset = 0
    if text.startswith("前天"):
        day_offset = 2
    elif text.startswith("昨天"):
        day_offset = 1
    elif text.startswith("今天"):
        day_offset = 0
    else:
        return None

    time_match = re.search(r"(\d{1,2}):(\d{2})", text)
    base = ref.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=day_offset)
    if time_match:
        return base.replace(hour=int(time_match.group(1)), minute=int(time_match.group(2)))
    return base


def is_thread_old_enough(
    posted_at: datetime | None,
    *,
    min_age_days: int,
    now: datetime | None = None,
) -> bool:
    """是否达到最小发帖龄期；未知日期保守保留（避免误跳）。"""
    if min_age_days <= 0:
        return True
    if posted_at is None:
        return True
    ref = now or datetime.now()
    if ref.tzinfo is not None:
        ref = ref.replace(tzinfo=None)
    cutoff = ref.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=min_age_days)
    compare = posted_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return compare <= cutoff


_THREAD_POSTED_RE = re.compile(
    r"发表于\s*(\d{4}-\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)"
    r'|title="(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)"',
    re.I,
)


def extract_thread_posted_at(html: str, *, now: datetime | None = None) -> datetime | None:
    """从帖页抽一楼发帖时间（发表于 / title 绝对时间）。"""
    if not html:
        return None
    m = _THREAD_POSTED_RE.search(html)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").strip()
    if not raw:
        return None
    # 绝对日期可走列表解析；带时分秒时先取日期部分再附时间
    abs_full = re.match(
        r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$",
        raw,
    )
    if abs_full:
        try:
            return datetime(
                int(abs_full.group(1)),
                int(abs_full.group(2)),
                int(abs_full.group(3)),
                int(abs_full.group(4) or 0),
                int(abs_full.group(5) or 0),
                int(abs_full.group(6) or 0),
            )
        except ValueError:
            return None
    return parse_discuz_list_datetime(raw, now=now)