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
