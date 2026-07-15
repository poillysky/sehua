"""crawl_pages 待抓队列：入队 / 取待抓 / 软文退避 / 完结。"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

SOFT_AD_ERROR = "soft_ad"
PENDING_EXCLUDE_SOFT = "AND COALESCE(last_error, '') NOT IN ('soft_ad', 'interstitial')"
PENDING_SOFT_ONLY = "AND COALESCE(last_error, '') IN ('soft_ad', 'interstitial')"
# 异常帖：非软文且曾失败/有错误标记（成功出队前一直留在异常队列）
PENDING_ABNORMAL_ONLY = (
    "AND COALESCE(last_error, '') NOT IN ('soft_ad', 'interstitial') "
    "AND (COALESCE(fetch_fail_count, 0) > 0 OR COALESCE(last_error, '') <> '')"
)
PENDING_NORMAL_ONLY = (
    "AND COALESCE(last_error, '') = '' AND COALESCE(fetch_fail_count, 0) = 0"
)
# 连续调度可抓：新帖 + 退避已到期的异常帖（仍排除软文）
PENDING_WORKABLE = (
    "AND COALESCE(last_error, '') NOT IN ('soft_ad', 'interstitial')"
)
PENDING_READY = "AND (retry_after IS NULL OR retry_after <= now())"
PENDING_ORDER = "ORDER BY COALESCE(fetch_fail_count, 0) ASC, updated_at ASC, created_at ASC"

# 同一帖连续重试上限：超出后出队为 failed，避免永远占异常队列空转
MAX_THREAD_RETRIES = 3
# 正常待抓积压阈值（不含异常/软文）：达到/超过则本轮不再扫列表，先消化正常队列
QUEUE_LIST_BACKPRESSURE = 150

_TID_RE = re.compile(r"thread-(\d+)-", re.I)
_TID_Q_RE = re.compile(r"(?:^|[?&])tid=(\d+)", re.I)
_VIEWTHREAD_RE = re.compile(r"forum\.php\?[^#]*mod=viewthread[^#]*[?&]tid=(\d+)", re.I)
_MOBILE_QUERY_RE = re.compile(r"(?:^|[?&])mobile=", re.I)


def tid_from_url(url: str) -> Optional[int]:
    u = (url or "").strip()
    if not u:
        return None
    for pattern in (_TID_RE, _VIEWTHREAD_RE, _TID_Q_RE):
        m = pattern.search(u)
        if m:
            return int(m.group(1))
    try:
        qs = parse_qs(urlparse(u).query)
        tid = (qs.get("tid") or [None])[0]
        if tid and str(tid).isdigit():
            return int(tid)
    except Exception:
        pass
    return None


def is_mobile_thread_url(url: str) -> bool:
    """识别手机版帖链接（m. 子域 / mobile= 参数）。"""
    u = (url or "").strip()
    if not u:
        return False
    try:
        p = urlparse(u if "://" in u else f"https://{u}")
    except Exception:
        return bool(_MOBILE_QUERY_RE.search(u))
    host = (p.netloc or "").lower()
    if host.startswith("m.") or host.startswith("mobile."):
        return True
    q = (p.query or "").lower()
    if "mobile=" in q and "mobile=no" not in q:
        return True
    return False


def _desktop_host(netloc: str) -> str:
    host = (netloc or "").strip().lower()
    if host.startswith("m."):
        return "www." + host[2:]
    if host.startswith("mobile."):
        return "www." + host[len("mobile.") :]
    return netloc


_CANON_SITE_HOST = "www.sehuatang.net"


def _canonical_site_host(netloc: str) -> str:
    """同一站点多入口（.net / .org / m.）统一成一个桌面主机，避免同 tid 双队列。"""
    host = _desktop_host(netloc or "")
    low = host.lower()
    if "sehuatang." in low:
        return _CANON_SITE_HOST
    return host or _CANON_SITE_HOST


def canonical_thread_url(url: str, *, root: str = "") -> str:
    """统一为桌面帖 URL：去掉 mobile / 跨域镜像，输出 https://www.sehuatang.net/thread-{tid}-1-1.html。"""
    u = (url or "").strip()
    tid = tid_from_url(u)
    if tid is None:
        return u

    host = _CANON_SITE_HOST
    if root:
        try:
            rp = urlparse(root if "://" in root else f"https://{root}")
            if rp.netloc:
                host = _canonical_site_host(rp.netloc)
        except Exception:
            pass
    else:
        parsed = urlparse(u if "://" in u else f"https://{u}")
        if parsed.netloc:
            host = _canonical_site_host(parsed.netloc)

    return f"https://{host}/thread-{tid}-1-1.html"


def dedupe_pending_by_tid(conn: Any, *, board_fid: str | int | None = None) -> int:
    """合并同 tid 多条 pending（常见于 .net/.org 双入口）。保留一条，其余标 skipped。"""
    cur = conn.cursor()
    board_clause = "AND board_fid = %s" if board_fid is not None else ""
    params: list[Any] = []
    if board_fid is not None:
        params.append(str(board_fid))
    cur.execute(
        f"""
        WITH ranked AS (
          SELECT url, tid,
                 ROW_NUMBER() OVER (
                   PARTITION BY tid
                   ORDER BY
                     CASE WHEN url LIKE 'https://www.sehuatang.net/%%' THEN 0 ELSE 1 END,
                     updated_at ASC,
                     created_at ASC
                 ) AS rn
          FROM crawl_pages
          WHERE page_type = 'thread'
            AND status = 'pending'
            AND tid IS NOT NULL
            {board_clause}
        )
        UPDATE crawl_pages AS cp
        SET status = 'skipped',
            outcome = 'duplicate_tid_url',
            updated_at = now()
        FROM ranked
        WHERE cp.url = ranked.url
          AND ranked.rn > 1
        """,
        params or None,
    )
    n = int(cur.rowcount or 0)
    if n:
        conn.commit()
    return n


def is_thread_known(conn: Any, url: str) -> bool:
    """URL（规范化后）是否已在 crawl_pages 中（任意状态）。"""
    url = canonical_thread_url(url)
    if not url:
        return False
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM crawl_pages WHERE page_type = 'thread' AND url = %s LIMIT 1",
        (url,),
    )
    return cur.fetchone() is not None


def known_thread_urls(conn: Any, urls: list[str]) -> set[str]:
    """批量查询哪些规范化 URL 已入库。"""
    canon = [canonical_thread_url(u) for u in urls if u]
    canon = list(dict.fromkeys(u for u in canon if u))
    if not canon:
        return set()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT url FROM crawl_pages
        WHERE page_type = 'thread' AND url IN %s
        """,
        (tuple(canon),),
    )
    return {str(r[0]) for r in cur.fetchall()}


def enqueue_thread(
    conn: Any,
    *,
    url: str,
    board_fid: str | int,
    board_name: str = "",
    title: str = "",
    forum_id: str = "sehuatang",
    retry_after: object | None = None,
) -> bool:
    """新帖入队；已存在则不覆盖状态。返回是否新插入。

    retry_after：龄期未满等场景先占位入队，到期后再被取队列抓取。
    """
    url = canonical_thread_url(url)
    tid = tid_from_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO crawl_pages (
          url, page_type, status, tid, board_fid, board_name, thread_title, forum_id,
          retry_after, created_at, updated_at
        )
        VALUES (%s, 'thread', 'pending', %s, %s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (url) DO NOTHING
        """,
        (
            url,
            tid,
            str(board_fid),
            board_name or None,
            title or None,
            forum_id,
            retry_after,
        ),
    )
    inserted = cur.rowcount > 0
    conn.commit()
    return inserted


def fetch_pending_threads(
    conn: Any,
    *,
    board_fid: str | int,
    limit: int = 50,
    include_soft_ad: bool = False,
    include_due_abnormal: bool = True,
) -> list[dict[str, Any]]:
    """取出可抓队列：默认 = 新帖 + 退避到期的异常帖（不含软文）。

    include_due_abnormal=False 时仅从未失败过的正常帖（旧行为）。
    """
    if include_soft_ad:
        extra = f"{PENDING_READY}"
    elif include_due_abnormal:
        extra = f"{PENDING_READY} {PENDING_WORKABLE}"
    else:
        extra = f"{PENDING_READY} {PENDING_NORMAL_ONLY}"
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT url, tid, thread_title, board_fid, board_name, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          AND board_fid = %s
          {extra}
        {PENDING_ORDER}
        LIMIT %s
        """,
        (str(board_fid), max(1, int(limit))),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_pending_abnormal(
    conn: Any,
    *,
    board_fid: str | int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """取出异常队列帖（忽略退避，供「异常重试」在队列内重爬）。"""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT url, tid, thread_title, board_fid, board_name, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          AND board_fid = %s
          {PENDING_ABNORMAL_ONLY}
        {PENDING_ORDER}
        LIMIT %s
        """,
        (str(board_fid), max(1, int(limit))),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_pending_soft_ad(
    conn: Any,
    *,
    board_fid: str | int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """取出软文队列帖（忽略退避，供「软文重试」在队列内重爬）。"""
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT url, tid, thread_title, board_fid, board_name, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          AND board_fid = %s
          {PENDING_SOFT_ONLY}
        {PENDING_ORDER}
        LIMIT %s
        """,
        (str(board_fid), max(1, int(limit))),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def count_pending(conn: Any, *, board_fid: str | int | None = None) -> dict[str, int]:
    cur = conn.cursor()
    board_clause = "AND board_fid = %s" if board_fid is not None else ""
    params: list[Any] = []
    if board_fid is not None:
        params.append(str(board_fid))

    def _count(extra: str) -> int:
        cur.execute(
            f"""
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread' AND status = 'pending' {board_clause} {extra}
            """,
            params or None,
        )
        return int(cur.fetchone()[0])

    ready = _count(f"{PENDING_READY} {PENDING_NORMAL_ONLY}")
    soft = _count(PENDING_SOFT_ONLY)
    abnormal = _count(PENDING_ABNORMAL_ONLY)
    deferred = _count("AND retry_after IS NOT NULL AND retry_after > now()")
    # 连续调度马上能吃的（含到期异常重试）
    workable = _count(f"{PENDING_READY} {PENDING_WORKABLE}")
    return {
        "ready": ready,
        "soft_ad": soft,
        "abnormal": abnormal,
        "deferred": deferred,
        "workable": workable,
        "total_pending": ready + soft + abnormal,
    }


def mark_pending_soft_ad(conn: Any, url: str, *, backoff_seconds: int = 3600) -> None:
    url = canonical_thread_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE crawl_pages
        SET last_error = %s,
            fetch_fail_count = COALESCE(fetch_fail_count, 0) + 1,
            retry_after = now() + (%s * interval '1 second'),
            updated_at = now()
        WHERE page_type = 'thread' AND status = 'pending' AND url = %s
        """,
        (SOFT_AD_ERROR, max(60, int(backoff_seconds)), url),
    )
    conn.commit()


def mark_pending_retry(conn: Any, url: str, error: str, *, backoff_seconds: int = 900) -> None:
    url = canonical_thread_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE crawl_pages
        SET last_error = %s,
            fetch_fail_count = COALESCE(fetch_fail_count, 0) + 1,
            retry_after = now() + (%s * interval '1 second'),
            status = 'pending',
            updated_at = now()
        WHERE page_type = 'thread' AND url = %s
        """,
        ((error or "retry")[:500], max(30, int(backoff_seconds)), url),
    )
    conn.commit()


def mark_thread_done(
    conn: Any,
    url: str,
    *,
    outcome: str,
    status: str = "done",
) -> None:
    url = canonical_thread_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE crawl_pages
        SET status = %s,
            outcome = %s,
            last_error = NULL,
            retry_after = NULL,
            crawled_at = now(),
            updated_at = now()
        WHERE page_type = 'thread' AND url = %s
        """,
        (status, (outcome or "")[:200], url),
    )
    conn.commit()


def mark_thread_skipped(conn: Any, url: str, outcome: str) -> None:
    mark_thread_done(conn, url, outcome=outcome, status="skipped")


def requeue_for_recrawl(
    conn: Any,
    *,
    url: str,
    board_fid: str | int,
    board_name: str = "",
    title: str = "",
    forum_id: str = "sehuatang",
) -> dict[str, Any]:
    """将已处理帖重新置为 pending，供已入库重爬。"""
    url = canonical_thread_url(url)
    tid = tid_from_url(url)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO crawl_pages (
          url, page_type, status, tid, board_fid, board_name, thread_title, forum_id,
          last_error, retry_after, fetch_fail_count, outcome, created_at, updated_at
        )
        VALUES (%s, 'thread', 'pending', %s, %s, %s, %s, %s, NULL, NULL, 0, NULL, now(), now())
        ON CONFLICT (url) DO UPDATE SET
          status = 'pending',
          tid = COALESCE(EXCLUDED.tid, crawl_pages.tid),
          board_fid = COALESCE(EXCLUDED.board_fid, crawl_pages.board_fid),
          board_name = COALESCE(EXCLUDED.board_name, crawl_pages.board_name),
          thread_title = COALESCE(EXCLUDED.thread_title, crawl_pages.thread_title),
          last_error = NULL,
          retry_after = NULL,
          fetch_fail_count = 0,
          outcome = NULL,
          crawled_at = NULL,
          updated_at = now()
        RETURNING url, tid, board_fid, status
        """,
        (
            url,
            tid,
            str(board_fid),
            board_name or None,
            title or None,
            forum_id,
        ),
    )
    row = cur.fetchone()
    conn.commit()
    return {
        "url": row[0],
        "tid": row[1],
        "board_fid": row[2],
        "status": row[3],
    }
