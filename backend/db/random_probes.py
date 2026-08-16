"""随机抓帖已探 tid 持久化 + 白名单板块 tid 范围估算。"""

from __future__ import annotations

import logging
import re
from typing import Any

from parsers.boards import parse_board_key

log = logging.getLogger(__name__)

_TID_RE = re.compile(r"(?:thread-|tid=|/t/)(\d+)", re.I)


def ensure_random_probes_schema(conn: Any) -> None:
    from db.migrate import run_migrations

    run_migrations(only={"026_random_tid_probes.sql"}, conn=conn, skip_crawl_conflicts=False)


def record_probe(
    conn: Any,
    *,
    forum_id: str,
    tid: int,
    outcome: str,
    board_fid: str | int | None = None,
    title: str | None = None,
) -> None:
    """写入/更新一次探测结果（幂等 upsert）。"""
    fid = (forum_id or "").strip() or "sehuatang"
    t = int(tid)
    if t <= 0:
        return
    out = (outcome or "probed").strip()[:40] or "probed"
    board = str(board_fid).strip() if board_fid is not None and str(board_fid).strip() else None
    tit = (title or "").strip()[:240] or None
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO random_tid_probes (forum_id, tid, outcome, board_fid, title, probed_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, now(), now())
        ON CONFLICT (forum_id, tid) DO UPDATE SET
          outcome = EXCLUDED.outcome,
          board_fid = COALESCE(EXCLUDED.board_fid, random_tid_probes.board_fid),
          title = COALESCE(EXCLUDED.title, random_tid_probes.title),
          updated_at = now()
        """,
        (fid, t, out, board, tit),
    )


def load_probed_tids(conn: Any, forum_id: str) -> set[int]:
    """加载该论坛全部已探 tid（用于抽样排除）。"""
    fid = (forum_id or "").strip() or "sehuatang"
    cur = conn.cursor()
    cur.execute("SELECT tid FROM random_tid_probes WHERE forum_id = %s", (fid,))
    return {int(r[0]) for r in cur.fetchall() if r and r[0] is not None}


def load_known_tids_for_exclude(
    meta_conn: Any,
    resource_conn: Any | None,
    *,
    forum_id: str,
    limit: int = 500_000,
) -> set[int]:
    """抽样前排除：crawl_pages 已有 tid + 资源库已解析出的 tid。

    避免深扫/扫新已入库帖再占随机探测名额。
    """
    fid = (forum_id or "").strip() or "sehuatang"
    lim = max(1, int(limit))
    tids: set[int] = set()

    try:
        cur = meta_conn.cursor()
        cur.execute(
            """
            SELECT tid FROM crawl_pages
            WHERE forum_id = %s
              AND page_type = 'thread'
              AND tid IS NOT NULL
            ORDER BY tid DESC
            LIMIT %s
            """,
            (fid, lim),
        )
        for row in cur.fetchall():
            if row and row[0]:
                tids.add(int(row[0]))
    except Exception:
        log.exception("load known tids from crawl_pages")
        raise

    if resource_conn is not None:
        try:
            cur = resource_conn.cursor()
            cur.execute(
                """
                SELECT source_url FROM resource_sources
                WHERE COALESCE(forum_id, '') IN (%s, '')
                  AND COALESCE(source_url, '') <> ''
                ORDER BY id DESC
                LIMIT %s
                """,
                (fid, lim),
            )
            for (url,) in cur.fetchall():
                t = _extract_tid(str(url or ""))
                if t:
                    tids.add(t)
        except Exception:
            log.exception("load known tids from resources")
            # 资源库失败不阻断：crawl_pages 已足够挡住大部分；单帖仍有 is_tid_known
    return tids


def count_probed(conn: Any, forum_id: str) -> int:
    fid = (forum_id or "").strip() or "sehuatang"
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM random_tid_probes WHERE forum_id = %s", (fid,))
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _probe_where(
    forum_id: str,
    *,
    outcome: str | None = None,
    q: str | None = None,
) -> tuple[str, list[Any]]:
    fid = (forum_id or "").strip() or "sehuatang"
    clauses = ["forum_id = %s"]
    params: list[Any] = [fid]
    out = (outcome or "").strip().lower()
    if out and out not in {"all", "*"}:
        clauses.append("outcome = %s")
        params.append(out)
    query = (q or "").strip()
    if query:
        clauses.append("(CAST(tid AS TEXT) LIKE %s OR COALESCE(title, '') ILIKE %s OR COALESCE(board_fid, '') ILIKE %s)")
        like = f"%{query}%"
        params.extend([like, like, like])
    return " AND ".join(clauses), params


def count_probes_filtered(
    conn: Any,
    forum_id: str,
    *,
    outcome: str | None = None,
    q: str | None = None,
) -> int:
    where, params = _probe_where(forum_id, outcome=outcome, q=q)
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM random_tid_probes WHERE {where}", params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def count_probes_by_outcome(conn: Any, forum_id: str) -> dict[str, int]:
    fid = (forum_id or "").strip() or "sehuatang"
    cur = conn.cursor()
    cur.execute(
        """
        SELECT outcome, COUNT(*) FROM random_tid_probes
        WHERE forum_id = %s
        GROUP BY outcome
        """,
        (fid,),
    )
    out: dict[str, int] = {}
    total = 0
    for row in cur.fetchall():
        key = str(row[0] or "probed")
        n = int(row[1] or 0)
        out[key] = n
        total += n
    out["total"] = total
    return out


def list_probes(
    conn: Any,
    forum_id: str,
    *,
    outcome: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    where, params = _probe_where(forum_id, outcome=outcome, q=q)
    lim = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT tid, outcome, board_fid, title, probed_at, updated_at
        FROM random_tid_probes
        WHERE {where}
        ORDER BY updated_at DESC, tid DESC
        LIMIT %s OFFSET %s
        """,
        [*params, lim, off],
    )
    rows: list[dict[str, Any]] = []
    for tid, oc, board, title, probed_at, updated_at in cur.fetchall():
        rows.append(
            {
                "tid": int(tid) if tid is not None else None,
                "outcome": str(oc or ""),
                "board_fid": board,
                "title": title or "",
                "probed_at": probed_at.isoformat() if probed_at is not None else None,
                "updated_at": updated_at.isoformat() if updated_at is not None else None,
                "status": str(oc or ""),
            }
        )
    return rows


def _enabled_board_matchers(enabled_keys: list[str] | tuple[str, ...] | None) -> tuple[list[str], list[str]]:
    """返回 (精确 board_fid keys, 纯 fid 字符串) 供 SQL 匹配。"""
    exact: list[str] = []
    bare: list[str] = []
    seen_e: set[str] = set()
    seen_b: set[str] = set()
    for raw in enabled_keys or []:
        k = str(raw).strip()
        if not k:
            continue
        if k not in seen_e:
            seen_e.add(k)
            exact.append(k)
        fid, _ = parse_board_key(k)
        if fid:
            b = str(fid)
            if b not in seen_b:
                seen_b.add(b)
                bare.append(b)
    return exact, bare


def _extract_tid(url: str) -> int | None:
    m = _TID_RE.search(url or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def collect_whitelist_tids(
    meta_conn: Any,
    resource_conn: Any | None,
    *,
    forum_id: str,
    enabled_keys: list[str] | tuple[str, ...] | None,
    limit: int = 50_000,
) -> list[int]:
    """从资源库 + 队列 + 已探成功记录收集白名单板块相关 tid。"""
    fid = (forum_id or "").strip() or "sehuatang"
    exact, bare = _enabled_board_matchers(enabled_keys)
    if not exact and not bare:
        return []
    tids: set[int] = set()

    # 1) crawl_pages（元数据库）
    try:
        cur = meta_conn.cursor()
        cur.execute(
            """
            SELECT tid FROM crawl_pages
            WHERE forum_id = %s
              AND page_type = 'thread'
              AND tid IS NOT NULL
              AND (
                board_fid = ANY(%s)
                OR split_part(COALESCE(board_fid, ''), ':', 1) = ANY(%s)
              )
            ORDER BY tid DESC
            LIMIT %s
            """,
            (fid, exact or [""], bare or [""], int(limit)),
        )
        for row in cur.fetchall():
            if row and row[0]:
                tids.add(int(row[0]))
    except Exception:
        log.exception("collect whitelist tids from crawl_pages")

    # 2) random_tid_probes 成功类
    try:
        cur = meta_conn.cursor()
        cur.execute(
            """
            SELECT tid FROM random_tid_probes
            WHERE forum_id = %s
              AND outcome IN ('import', 'stub', 'skipped')
              AND (
                board_fid = ANY(%s)
                OR split_part(COALESCE(board_fid, ''), ':', 1) = ANY(%s)
                OR board_fid IS NULL
              )
            ORDER BY tid DESC
            LIMIT %s
            """,
            (fid, exact or [""], bare or [""], int(limit)),
        )
        for row in cur.fetchall():
            if row and row[0]:
                tids.add(int(row[0]))
    except Exception:
        log.exception("collect whitelist tids from probes")

    # 3) resource_sources
    if resource_conn is not None:
        try:
            cur = resource_conn.cursor()
            cur.execute(
                """
                SELECT source_url, board_fid FROM resource_sources
                WHERE COALESCE(forum_id, '') IN (%s, '')
                  AND (
                    board_fid = ANY(%s)
                    OR split_part(COALESCE(board_fid, ''), ':', 1) = ANY(%s)
                  )
                  AND COALESCE(source_url, '') <> ''
                ORDER BY id DESC
                LIMIT %s
                """,
                (fid, exact or [""], bare or [""], int(limit)),
            )
            for url, _bf in cur.fetchall():
                t = _extract_tid(str(url or ""))
                if t:
                    tids.add(t)
        except Exception:
            log.exception("collect whitelist tids from resources")

    return sorted(tids)


def estimate_tid_range(
    whitelist_tids: list[int],
    *,
    cfg_lo: int,
    cfg_hi: int,
    pad_ratio: float = 0.08,
    min_samples: int = 30,
) -> dict[str, Any]:
    """根据白名单帖号分布估算更准的抽样上下界与加权窗口。

    样本不足时回退 cfg_lo/cfg_hi。
    """
    low = min(int(cfg_lo), int(cfg_hi))
    high = max(int(cfg_lo), int(cfg_hi))
    out: dict[str, Any] = {
        "lo": low,
        "hi": high,
        "adaptive": False,
        "sample_n": len(whitelist_tids or []),
        "windows": [(low, high, 1.0)],
        "p10": None,
        "p50": None,
        "p90": None,
    }
    nums = sorted(int(x) for x in (whitelist_tids or []) if int(x) > 0)
    out["sample_n"] = len(nums)
    if len(nums) < int(min_samples):
        return out

    def _pct(p: float) -> int:
        if not nums:
            return low
        i = int(round((len(nums) - 1) * p))
        i = max(0, min(len(nums) - 1, i))
        return int(nums[i])

    p10, p50, p90 = _pct(0.10), _pct(0.50), _pct(0.90)
    span = max(1, p90 - p10)
    pad = max(500, int(span * float(pad_ratio)))
    core_lo = max(low, p10 - pad)
    core_hi = min(high, p90 + pad)
    if core_hi <= core_lo:
        core_lo, core_hi = low, high

    # 三窗：核心密集区权重大；两侧探索区较小（挖更早/更新）
    mid = max(core_lo, min(core_hi, p50))
    left_hi = max(core_lo, mid)
    right_lo = min(core_hi, mid)
    windows: list[tuple[int, int, float]] = [
        (core_lo, left_hi, 0.45),
        (right_lo, core_hi, 0.40),
        (low, high, 0.15),  # 全局探索，避免永远困在已知带
    ]
    # 去退化空窗
    windows = [(a, b, w) for a, b, w in windows if b > a and w > 0]
    if not windows:
        windows = [(low, high, 1.0)]

    out.update(
        {
            "lo": core_lo,
            "hi": core_hi,
            "adaptive": True,
            "windows": windows,
            "p10": p10,
            "p50": p50,
            "p90": p90,
        }
    )
    return out
