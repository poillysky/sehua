"""crawl_pages 待抓队列：入队 / 取待抓 / 软文退避 / 完结。"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

SOFT_AD_ERROR = "soft_ad"
# 历史软文标记；现与异常帖同一队列，识别/重试逻辑一致
_SOFT_AD_MARKERS = ("soft_ad", "interstitial")
# 异常帖（含原软文壳）：曾失败或有错误标记
PENDING_ABNORMAL_ONLY = (
    "AND (COALESCE(fetch_fail_count, 0) > 0 OR COALESCE(last_error, '') <> '')"
)
PENDING_NORMAL_ONLY = (
    "AND COALESCE(last_error, '') = '' AND COALESCE(fetch_fail_count, 0) = 0"
)
# 兼容旧调用：软文 = 异常中的历史 soft_ad/interstitial 子集
PENDING_SOFT_ONLY = (
    "AND COALESCE(last_error, '') IN ('soft_ad', 'interstitial')"
)
# 连续调度可抓：新帖 + 到期的异常/软文（同一重试池）
PENDING_WORKABLE = ""
PENDING_READY = "AND (retry_after IS NULL OR retry_after <= now())"
PENDING_ORDER = "ORDER BY COALESCE(fetch_fail_count, 0) ASC, updated_at ASC, created_at ASC"

# 同一帖连续重试上限：超出后出队为 failed，避免永远占异常队列空转
MAX_THREAD_RETRIES = 3
# 正常待抓积压阈值（不含异常队列）：达到/超过则本轮不再扫列表


def _as_board_keys(board_fid: str | int | list[str | int] | tuple[str | int, ...] | None) -> list[str]:
    if board_fid is None:
        return []
    if isinstance(board_fid, (list, tuple, set)):
        return [str(x).strip() for x in board_fid if str(x).strip()]
    key = str(board_fid).strip()
    return [key] if key else []


def _board_fid_sql(
    board_fid: str | int | list[str | int] | tuple[str | int, ...] | None,
) -> tuple[str, list[Any]]:
    keys = _as_board_keys(board_fid)
    if not keys:
        return "", []
    if len(keys) == 1:
        return "AND board_fid = %s", [keys[0]]
    return "AND board_fid = ANY(%s)", [keys]
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


def dedupe_pending_by_tid(
    conn: Any, *, board_fid: str | int | list[str | int] | tuple[str | int, ...] | None = None
) -> int:
    """合并同 tid 多条 pending（常见于 .net/.org 双入口）。保留一条，其余标 skipped。"""
    cur = conn.cursor()
    board_clause, params = _board_fid_sql(board_fid)
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
    board_fid: str | int | list[str | int] | tuple[str | int, ...],
    limit: int = 50,
    include_soft_ad: bool = False,
    include_due_abnormal: bool = True,
) -> list[dict[str, Any]]:
    """取出可抓队列：默认 = 新帖 + 退避到期的异常/软文（同一重试池）。"""
    if include_soft_ad or include_due_abnormal:
        extra = f"{PENDING_READY}".strip()
    else:
        extra = f"{PENDING_READY} {PENDING_NORMAL_ONLY}"
    board_clause, params = _board_fid_sql(board_fid)
    if not board_clause:
        return []
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT url, tid, thread_title, board_fid, board_name, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          {board_clause}
          {extra}
        {PENDING_ORDER}
        LIMIT %s
        """,
        (*params, max(1, int(limit))),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_pending_abnormal(
    conn: Any,
    *,
    board_fid: str | int | list[str | int] | tuple[str | int, ...],
    limit: int = 50,
) -> list[dict[str, Any]]:
    """取出异常队列帖（含原软文；忽略退避，供手动重试）。"""
    board_clause, params = _board_fid_sql(board_fid)
    if not board_clause:
        return []
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT url, tid, thread_title, board_fid, board_name, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          {board_clause}
          {PENDING_ABNORMAL_ONLY}
        {PENDING_ORDER}
        LIMIT %s
        """,
        (*params, max(1, int(limit))),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_pending_soft_ad(
    conn: Any,
    *,
    board_fid: str | int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """兼容旧接口：与异常队列相同。"""
    return fetch_pending_abnormal(conn, board_fid=board_fid, limit=limit)


def _pending_queue_kind_clause(kind: str) -> str:
    key = (kind or "").strip().lower()
    if key == "abnormal":
        return PENDING_ABNORMAL_ONLY
    if key == "ready":
        return f"{PENDING_READY} {PENDING_NORMAL_ONLY}"
    raise ValueError("kind 仅支持 ready / abnormal")


def _pending_queue_search_clause(q: str | None) -> tuple[str, list[Any]]:
    text = (q or "").strip()
    if not text:
        return "", []
    like = f"%{text}%"
    tid_num: int | None = None
    if text.isdigit():
        try:
            tid_num = int(text)
        except ValueError:
            tid_num = None
    if tid_num is not None and tid_num > 0:
        return (
            """
            AND (
              tid = %s
              OR url ILIKE %s
              OR COALESCE(thread_title, '') ILIKE %s
              OR COALESCE(last_error, '') ILIKE %s
              OR COALESCE(board_name, '') ILIKE %s
              OR COALESCE(board_fid, '') ILIKE %s
            )
            """,
            [tid_num, like, like, like, like, like],
        )
    return (
        """
        AND (
          url ILIKE %s
          OR COALESCE(thread_title, '') ILIKE %s
          OR COALESCE(last_error, '') ILIKE %s
          OR COALESCE(board_name, '') ILIKE %s
          OR COALESCE(board_fid, '') ILIKE %s
          OR CAST(COALESCE(tid, 0) AS TEXT) ILIKE %s
        )
        """,
        [like, like, like, like, like, like],
    )


def count_pending_queue(
    conn: Any,
    *,
    kind: str,
    board_fid: str | int | list[str | int] | tuple[str | int, ...] | None = None,
    q: str | None = None,
    reason: str | None = None,
) -> int:
    """待抓队列计数：ready=正常可抓，abnormal=异常池（含未到期）。"""
    kind_sql = _pending_queue_kind_clause(kind)
    board_clause, board_params = _board_fid_sql(board_fid)
    q_sql, q_params = _pending_queue_search_clause(q)
    reason_sql, reason_params = _exact_reason_clause(PENDING_REASON_EXPR, reason)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*) FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          {board_clause}
          {kind_sql}
          {q_sql}
          {reason_sql}
        """,
        [*board_params, *q_params, *reason_params] or None,
    )
    return int(cur.fetchone()[0] or 0)


def list_pending_reasons(
    conn: Any,
    *,
    kind: str,
    board_fid: str | int | list[str | int] | tuple[str | int, ...] | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """待抓队列原因分组（供下拉筛选）。"""
    kind_sql = _pending_queue_kind_clause(kind)
    board_clause, board_params = _board_fid_sql(board_fid)
    q_sql, q_params = _pending_queue_search_clause(q)
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {PENDING_REASON_EXPR} AS reason, COUNT(*) AS cnt
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          {board_clause}
          {kind_sql}
          {q_sql}
          AND {PENDING_REASON_EXPR} <> ''
        GROUP BY 1
        ORDER BY cnt DESC, reason ASC
        LIMIT 80
        """,
        [*board_params, *q_params] or None,
    )
    return [{"reason": str(r[0]), "count": int(r[1] or 0)} for r in cur.fetchall() if r and r[0]]


def list_pending_queue(
    conn: Any,
    *,
    kind: str,
    board_fid: str | int | list[str | int] | tuple[str | int, ...] | None = None,
    q: str | None = None,
    reason: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """待抓队列明细分页。"""
    kind_sql = _pending_queue_kind_clause(kind)
    board_clause, board_params = _board_fid_sql(board_fid)
    q_sql, q_params = _pending_queue_search_clause(q)
    reason_sql, reason_params = _exact_reason_clause(PENDING_REASON_EXPR, reason)
    lim = max(1, min(200, int(limit)))
    off = max(0, int(offset))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
          url, tid, thread_title, board_fid, board_name, forum_id,
          status, outcome, last_error, fetch_fail_count, retry_after,
          crawled_at, created_at, updated_at
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = 'pending'
          {board_clause}
          {kind_sql}
          {q_sql}
          {reason_sql}
        {PENDING_ORDER}
        LIMIT %s OFFSET %s
        """,
        [*board_params, *q_params, *reason_params, lim, off],
    )
    cols = [d[0] for d in cur.description]
    rows: list[dict[str, Any]] = []
    for row in cur.fetchall():
        item = dict(zip(cols, row))
        for key in ("crawled_at", "created_at", "updated_at", "retry_after"):
            val = item.get(key)
            if hasattr(val, "isoformat"):
                item[key] = val.isoformat()
        rows.append(item)
    return rows


def count_pending(
    conn: Any, *, board_fid: str | int | list[str | int] | tuple[str | int, ...] | None = None
) -> dict[str, int]:
    cur = conn.cursor()
    board_clause, params = _board_fid_sql(board_fid)

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
    abnormal = _count(PENDING_ABNORMAL_ONLY)
    deferred = _count("AND retry_after IS NOT NULL AND retry_after > now()")
    workable = _count(PENDING_READY)
    return {
        "ready": ready,
        "soft_ad": 0,
        "abnormal": abnormal,
        "deferred": deferred,
        "workable": workable,
        "total_pending": ready + abnormal,
    }


def mark_pending_soft_ad(conn: Any, url: str, *, backoff_seconds: int = 3600) -> None:
    """兼容旧名：软文失败与异常同一套 mark_pending_retry。"""
    mark_pending_retry(conn, url, SOFT_AD_ERROR, backoff_seconds=backoff_seconds)

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


# 已出队且未正常入库/占位：失败（含重试耗尽）与跳过
DISCARDED_STATUSES = ("failed", "skipped")

# 可一键重新入队 / 账号爬未处理的类别（outcome 模糊匹配；空 patterns = 不限 outcome）
DISCARDED_REQUEUE_KINDS: dict[str, dict[str, Any]] = {
    "failed_all": {
        "label": "失败（全部）",
        "status": "failed",
        "outcome_patterns": (),
    },
    "access_denied_bad_title": {
        # 兼容旧 kind 名；现匹配所有「无阅读权限」跳过（含非正常标题 / 无有效标题）
        "label": "无阅读权限（跳过）",
        "status": "skipped",
        "outcome_patterns": (
            "%无阅读权限%",
        ),
    },
}

# 账号爬未处理顺序：先失败，再无阅读权限跳过
ACCOUNT_DISCARDED_KINDS: tuple[str, ...] = ("failed_all", "access_denied_bad_title")


def _discarded_kind_outcome_clause(kind: str) -> tuple[str, list[Any]]:
    meta = DISCARDED_REQUEUE_KINDS.get(kind)
    if not meta:
        raise ValueError(f"未知类别: {kind}")
    patterns = list(meta.get("outcome_patterns") or [])
    if not patterns:
        return "TRUE", []
    parts = ["COALESCE(outcome, '') ILIKE %s"] * len(patterns)
    return "(" + " OR ".join(parts) + ")", patterns


def count_discarded_kind(conn: Any, kind: str, *, forum_id: str | None = None) -> int:
    """统计某一可重跑类别的条数。"""
    meta = DISCARDED_REQUEUE_KINDS[kind]
    st = str(meta.get("status") or "skipped")
    out_sql, out_params = _discarded_kind_outcome_clause(kind)
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT COUNT(*) FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = %s
          AND {out_sql}
          {forum_sql}
        """,
        [st, *out_params, *forum_params],
    )
    return int(cur.fetchone()[0] or 0)


def list_discarded_kind(
    conn: Any,
    kind: str,
    *,
    limit: int = 1,
    exclude_urls: list[str] | None = None,
    forum_id: str | None = None,
) -> list[dict[str, Any]]:
    """按类别取未处理帖（用于账号爬一并处理）。"""
    meta = DISCARDED_REQUEUE_KINDS[kind]
    st = str(meta.get("status") or "skipped")
    out_sql, out_params = _discarded_kind_outcome_clause(kind)
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    excl = [str(u).strip() for u in (exclude_urls or []) if str(u).strip()]
    excl_sql = ""
    excl_params: list[Any] = []
    if excl:
        excl_sql = "AND NOT (url = ANY(%s))"
        excl_params = [excl]
    lim = max(1, min(100, int(limit)))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
          url, tid, thread_title, board_fid, board_name, forum_id,
          status, outcome, last_error, fetch_fail_count
        FROM crawl_pages
        WHERE page_type = 'thread'
          AND status = %s
          AND {out_sql}
          {forum_sql}
          {excl_sql}
        ORDER BY COALESCE(crawled_at, updated_at) ASC, updated_at ASC
        LIMIT %s
        """,
        [st, *out_params, *forum_params, *excl_params, lim],
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def requeue_discarded_kind(conn: Any, kind: str, *, forum_id: str | None = None) -> int:
    """将某一类失败/跳过帖重新置为 pending，供再次抓取判定。"""
    meta = DISCARDED_REQUEUE_KINDS[kind]
    st = str(meta.get("status") or "skipped")
    out_sql, out_params = _discarded_kind_outcome_clause(kind)
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE crawl_pages
        SET status = 'pending',
            last_error = NULL,
            retry_after = NULL,
            fetch_fail_count = 0,
            outcome = NULL,
            crawled_at = NULL,
            updated_at = now()
        WHERE page_type = 'thread'
          AND status = %s
          AND {out_sql}
          {forum_sql}
        """,
        [st, *out_params, *forum_params],
    )
    n = int(cur.rowcount or 0)
    if n:
        conn.commit()
    return n


def _discarded_status_clause(
    status: str | list[str] | tuple[str, ...] | None,
) -> tuple[str, list[Any]]:
    if status is None or status == "" or status == "all":
        return "AND status = ANY(%s)", [list(DISCARDED_STATUSES)]
    if isinstance(status, (list, tuple, set)):
        keys = [str(s).strip() for s in status if str(s).strip() in DISCARDED_STATUSES]
        if not keys:
            keys = list(DISCARDED_STATUSES)
        return "AND status = ANY(%s)", [keys]
    key = str(status).strip()
    if key not in DISCARDED_STATUSES:
        return "AND status = ANY(%s)", [list(DISCARDED_STATUSES)]
    return "AND status = %s", [key]


def _discarded_search_clause(q: str | None) -> tuple[str, list[Any]]:
    text = (q or "").strip()
    if not text:
        return "", []
    like = f"%{text}%"
    tid_num: int | None = None
    if text.isdigit():
        try:
            tid_num = int(text)
        except ValueError:
            tid_num = None
    if tid_num is not None and tid_num > 0:
        return (
            """
            AND (
              tid = %s
              OR url ILIKE %s
              OR COALESCE(thread_title, '') ILIKE %s
              OR COALESCE(outcome, '') ILIKE %s
              OR COALESCE(board_name, '') ILIKE %s
              OR COALESCE(board_fid, '') ILIKE %s
            )
            """,
            [tid_num, like, like, like, like, like],
        )
    return (
        """
        AND (
          url ILIKE %s
          OR COALESCE(thread_title, '') ILIKE %s
          OR COALESCE(outcome, '') ILIKE %s
          OR COALESCE(board_name, '') ILIKE %s
          OR COALESCE(board_fid, '') ILIKE %s
          OR CAST(COALESCE(tid, 0) AS TEXT) ILIKE %s
        )
        """,
        [like, like, like, like, like, like],
    )


# 明细「原因」列：优先 outcome，其次 last_error（与前端 discardedReason 对齐）
DISCARDED_REASON_EXPR = (
    "COALESCE(NULLIF(TRIM(outcome), ''), NULLIF(TRIM(last_error), ''), '')"
)
PENDING_REASON_EXPR = (
    "COALESCE(NULLIF(TRIM(last_error), ''), NULLIF(TRIM(outcome), ''), '')"
)


def _exact_reason_clause(expr: str, reason: str | None) -> tuple[str, list[Any]]:
    text = (reason or "").strip()
    if not text:
        return "", []
    return f"AND {expr} = %s", [text]


def count_discarded(
    conn: Any,
    *,
    status: str | list[str] | tuple[str, ...] | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
    reason: str | None = None,
) -> dict[str, int]:
    """已出队未正常处理：failed / skipped 计数。"""
    cur = conn.cursor()
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    q_sql, q_params = _discarded_search_clause(q)
    reason_sql, reason_params = _exact_reason_clause(DISCARDED_REASON_EXPR, reason)

    def _n(status_key: str | None) -> int:
        st_sql, st_params = _discarded_status_clause(status_key)
        cur.execute(
            f"""
            SELECT COUNT(*) FROM crawl_pages
            WHERE page_type = 'thread'
              {st_sql}
              {forum_sql}
              {q_sql}
              {reason_sql}
            """,
            [*st_params, *forum_params, *q_params, *reason_params] or None,
        )
        return int(cur.fetchone()[0])

    failed = _n("failed")
    skipped = _n("skipped")
    if status in (None, "", "all"):
        total = failed + skipped
    elif str(status).strip() == "failed":
        total = failed
    elif str(status).strip() == "skipped":
        total = skipped
    else:
        total = _n(status)
    return {"failed": failed, "skipped": skipped, "total": total}


def list_discarded_reasons(
    conn: Any,
    *,
    status: str | list[str] | tuple[str, ...] | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    """未处理明细的原因分组（供下拉筛选，不含当前 reason 过滤）。"""
    cur = conn.cursor()
    st_sql, st_params = _discarded_status_clause(status)
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    q_sql, q_params = _discarded_search_clause(q)
    cur.execute(
        f"""
        SELECT {DISCARDED_REASON_EXPR} AS reason, COUNT(*) AS cnt
        FROM crawl_pages
        WHERE page_type = 'thread'
          {st_sql}
          {forum_sql}
          {q_sql}
          AND {DISCARDED_REASON_EXPR} <> ''
        GROUP BY 1
        ORDER BY cnt DESC, reason ASC
        LIMIT 80
        """,
        [*st_params, *forum_params, *q_params] or None,
    )
    return [{"reason": str(r[0]), "count": int(r[1] or 0)} for r in cur.fetchall() if r and r[0]]


def list_discarded(
    conn: Any,
    *,
    status: str | list[str] | tuple[str, ...] | None = "all",
    forum_id: str | None = None,
    q: str | None = None,
    reason: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """明细：入队后最终失败或跳过（非 done 入库/占位）。"""
    cur = conn.cursor()
    st_sql, st_params = _discarded_status_clause(status)
    forum = (forum_id or "").strip()
    forum_sql = "AND forum_id = %s" if forum else ""
    forum_params: list[Any] = [forum] if forum else []
    q_sql, q_params = _discarded_search_clause(q)
    reason_sql, reason_params = _exact_reason_clause(DISCARDED_REASON_EXPR, reason)
    lim = max(1, min(200, int(limit)))
    off = max(0, int(offset))
    cur.execute(
        f"""
        SELECT
          url, tid, thread_title, board_fid, board_name, forum_id,
          status, outcome, last_error, fetch_fail_count,
          crawled_at, created_at, updated_at
        FROM crawl_pages
        WHERE page_type = 'thread'
          {st_sql}
          {forum_sql}
          {q_sql}
          {reason_sql}
        ORDER BY COALESCE(crawled_at, updated_at) DESC, updated_at DESC
        LIMIT %s OFFSET %s
        """,
        [*st_params, *forum_params, *q_params, *reason_params, lim, off],
    )
    cols = [d[0] for d in cur.description]
    rows: list[dict[str, Any]] = []
    for row in cur.fetchall():
        item = dict(zip(cols, row))
        for key in ("crawled_at", "created_at", "updated_at"):
            val = item.get(key)
            if hasattr(val, "isoformat"):
                item[key] = val.isoformat()
        rows.append(item)
    return rows


def update_crawl_board_meta_by_tids(
    conn: Any,
    tids: list[int],
    *,
    board_fid: str | int,
    board_name: str = "",
) -> int:
    """按 tid 批量更新 crawl_pages 板块字段（与资源回填对齐）。"""
    clean = sorted({int(t) for t in tids if t is not None and int(t) > 0})
    if not clean:
        return 0
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE crawl_pages
        SET board_fid = %s,
            board_name = %s,
            updated_at = now()
        WHERE page_type = 'thread'
          AND tid = ANY(%s)
        """,
        (str(board_fid), board_name or None, clean),
    )
    n = int(cur.rowcount or 0)
    if n:
        conn.commit()
    return n


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
