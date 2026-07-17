"""拓扑「扫列表」：手动扫新帖捕新 + 连续/立即爬取仅深扫。

策略:
1. 手动扫新帖：从进度页起捕新，连续 N 页全已知或达上限后结束（不写每日闸门）。
2. 深扫：每轮翻 pages_per_board 页，下轮从游标续扫，直到空页/内容重复判定板底。
3. 深扫到底判定：列表空页，或连续两页主题 tid 集合相同，或与第 1 页 tid 相同（超页夹回）。
4. 龄期板（如 141）：仅入队发帖已满 min_thread_age_days 的帖；未满龄直接跳过，不入队。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

from crawler.fetcher import Fetcher
from crawler.list_urls import list_url_for_board, resolve_page_cap, site_root
from crawler.parser import ThreadBrief, is_valid_forum_list, parse_forum_list
from crawler.session import SessionManager
from crawler.throttle import THROTTLE
from db.connection import connect
from db.queue import enqueue_thread, update_crawl_board_meta_by_tids
from db.repository import known_resource_tids, update_board_meta_by_tids
from parsers.boards import get_board_policy
from parsers.list_dates import is_thread_old_enough
from parsers.thread_gates import is_thread_login_required

log = logging.getLogger(__name__)

LogFn = Callable[[str], None]

# 深扫连续「全已知」页数达到该值则早停（可配置覆盖；深扫已不再用此硬停）
DEFAULT_KNOWN_STOP_PAGES = 2
# 每日首页捕新安全上限（页）；正常以「扫到全已知页」结束
DEFAULT_HEAD_PAGES = 50
# 绝对兜底，防异常死循环（Discuz threadmaxpages 常见 ≤2000）
ABSOLUTE_PAGE_CEILING = 50_000


@dataclass
class ListScanResult:
    board_fid: int
    pages_scanned: list[int] = field(default_factory=list)  # 计入配额的页
    pages_head: list[int] = field(default_factory=list)  # 首页捕新（不计配额）
    pages_skipped: list[int] = field(default_factory=list)  # 兼容旧字段
    threads: list[ThreadBrief] = field(default_factory=list)
    enqueued: int = 0
    board_updated: int = 0  # 已有资源仅改板块字段
    deferred_young: int = 0  # 未满龄跳过（不入队）数
    last_list_page: int = 0  # 计数阶段最后一页（游标）
    harvest_start_page: int = 0
    list_exhausted: bool = False
    deep_early_stop: bool = False
    head_skipped: bool = False  # 今日已捕新，本轮跳过首页
    head_completed: bool = False  # 本轮扫到全已知页，可标记今日完成
    head_incomplete: bool = False  # 触及安全上限/失败，需下轮续扫首页
    head_progress_page: int = 0  # 下轮首页应从哪页续（0=无需）
    login_required: bool = False
    fetch_failures: int = 0
    errors: list[str] = field(default_factory=list)


def _tid_set(batch: list[ThreadBrief]) -> frozenset[int]:
    return frozenset(int(t.tid) for t in batch if getattr(t, "tid", None) is not None)


def _page_hard_limit(max_list_pages: int) -> int:
    """可选配置硬上限；未配置则仅保留绝对兜底。"""
    global_cap = int(max_list_pages or 0)
    if global_cap <= 0:
        return ABSOLUTE_PAGE_CEILING
    return min(global_cap, ABSOLUTE_PAGE_CEILING)


def counted_resume_page(last_list_page: int) -> int:
    """深扫起点：有游标则从该页（含）续扫；无游标从第 1 页。

    例：last=5 → 返回 5；last=0/1 → 返回 1（清游标后从头）。
    """
    cursor = max(0, int(last_list_page or 0))
    if cursor >= 2:
        return cursor
    return 1


def age_retry_after(
    posted_at: datetime | None,
    min_age_days: int,
) -> datetime | None:
    """未满龄帖的可抓时刻：发帖日 0 点 + min_age_days。"""
    if min_age_days <= 0 or posted_at is None:
        return None
    day = posted_at.replace(hour=0, minute=0, second=0, microsecond=0)
    if posted_at.tzinfo is not None:
        day = day.replace(tzinfo=None)
    return day + timedelta(days=int(min_age_days))


@dataclass
class _PageFetch:
    ok: bool
    batch: list[ThreadBrief] = field(default_factory=list)
    login_required: bool = False
    empty_list: bool = False
    error: str = ""


async def _fetch_list_page(
    fetcher: Fetcher,
    *,
    board_fid: int | str,
    page: int,
    root: str,
    pol,
) -> _PageFetch:
    """拉取列表页；不在此做龄期过滤（留给入队侧拆分即时/延期）。"""
    url = list_url_for_board(board_fid, page, root=root, policy=pol)
    try:
        html = await fetcher.get_list_html(url)
        THROTTLE.record_success()
    except Exception as exc:
        THROTTLE.record_failure()
        try:
            await fetcher.session.bootstrap(force=True, start_url=root)
            html = await fetcher.get_list_html(url)
            THROTTLE.record_success()
        except Exception as retry_exc:
            THROTTLE.record_failure()
            return _PageFetch(ok=False, error=f"page={page} retry: {retry_exc}")

    if SessionManager.is_safe_shell(html):
        THROTTLE.record_failure()
        try:
            await fetcher.session.bootstrap(force=True, start_url=root)
        except Exception:
            pass
        return _PageFetch(ok=False, error=f"page={page}: safe-shell")

    if is_thread_login_required(html) and not is_valid_forum_list(html):
        return _PageFetch(ok=False, login_required=True, error=f"page={page}: login-required")

    if not is_valid_forum_list(html):
        THROTTLE.record_failure()
        return _PageFetch(ok=False, error=f"page={page}: invalid list html")

    batch = parse_forum_list(
        html,
        base_url=root,
        skip_sticky=True,
        min_thread_age_days=0,
    )
    if not batch:
        return _PageFetch(ok=True, empty_list=True, batch=[])
    return _PageFetch(ok=True, batch=batch)


def _enqueue_batch(
    out: ListScanResult,
    batch: list[ThreadBrief],
    *,
    seen: set[int],
    board_fid: int | str,
    board_name: str,
    persist_enqueue: bool,
    min_thread_age_days: int = 0,
) -> tuple[int, int]:
    """入队缺失帖；已有资源只改板块字段不读帖。

    返回 (本页新插入数, 本页因未满龄跳过数)。未满龄帖不入队。
    """
    page_enqueued = 0
    page_skipped_young = 0
    if not batch:
        return 0, 0
    if persist_enqueue:
        conn = connect()
        try:
            tids = [int(t.tid) for t in batch if getattr(t, "tid", None)]
            known = known_resource_tids(conn, tids) if tids else set()
            to_update = [tid for tid in tids if tid in known and tid not in seen]
            # 去重后再更新，避免同页重复 tid
            to_update = list(dict.fromkeys(to_update))
            if to_update:
                n = update_board_meta_by_tids(
                    conn,
                    to_update,
                    board_fid=str(board_fid),
                    board_name=board_name,
                )
                update_crawl_board_meta_by_tids(
                    conn,
                    to_update,
                    board_fid=board_fid,
                    board_name=board_name,
                )
                out.board_updated += max(0, int(n or 0))
                for tid in to_update:
                    seen.add(tid)
            for t in batch:
                if t.tid in seen:
                    continue
                seen.add(t.tid)
                if t.tid in known:
                    continue
                if min_thread_age_days > 0 and not is_thread_old_enough(
                    t.posted_at,  # type: ignore[arg-type]
                    min_age_days=min_thread_age_days,
                ):
                    out.deferred_young += 1
                    page_skipped_young += 1
                    continue
                out.threads.append(t)
                if enqueue_thread(
                    conn,
                    url=t.url,
                    board_fid=board_fid,
                    board_name=board_name,
                    title=t.title,
                    retry_after=None,
                ):
                    out.enqueued += 1
                    page_enqueued += 1
        finally:
            conn.close()
    else:
        for t in batch:
            if t.tid in seen:
                continue
            seen.add(t.tid)
            if min_thread_age_days > 0 and not is_thread_old_enough(
                t.posted_at,  # type: ignore[arg-type]
                min_age_days=min_thread_age_days,
            ):
                out.deferred_young += 1
                page_skipped_young += 1
                continue
            out.threads.append(t)
    return page_enqueued, page_skipped_young


async def scan_board_list(
    fetcher: Fetcher,
    *,
    board_fid: int | str,
    pages_per_board: int = 15,
    max_list_pages: int = 0,
    head_pages: int = DEFAULT_HEAD_PAGES,
    known_stop_pages: int = DEFAULT_KNOWN_STOP_PAGES,
    scan_head: bool = True,
    deep_scan: bool = True,
    head_start_page: int = 1,
    entry_url: str = "",
    last_list_page: int = 0,
    board_name: str = "",
    persist_enqueue: bool = True,
    on_log: Optional[LogFn] = None,
) -> ListScanResult:
    """扫列表并入队。

    规则：
    1. scan_head=True：从 head_start_page 起捕新，直到连续 known_stop_pages 页全已知（默认 2）或触顶。
    2. deep_scan=False：捕新结束后返回（手动「扫新帖」）。
    3. scan_head=False + deep_scan=True：跳过首页，仅深扫（自动循环 / 立即爬取）。
    4. 深扫每轮 pages_per_board 页，跨轮从游标续扫直到空页或内容重复（板底）。
    5. 列表页失败不推进游标。
    6. 龄期板仅入队已满龄帖；未满龄跳过，不入队。
    """
    pol = get_board_policy(board_fid)
    numeric_fid = int(pol.fid)
    root = site_root(entry_url)
    harvest_quota = resolve_page_cap(pages_per_board, max_list_pages)
    page_limit = _page_hard_limit(max_list_pages)
    cursor = max(0, int(last_list_page or 0))
    head_cap = max(1, int(head_pages or DEFAULT_HEAD_PAGES))
    # 扫新帖：连续 N 页全已知则结束（默认 2）；深扫仍以空页/内容重复到底
    head_known_need = int(known_stop_pages or 0)
    if head_known_need <= 0:
        head_known_need = DEFAULT_KNOWN_STOP_PAGES
    head_known_need = max(1, head_known_need)
    min_age = int(pol.min_thread_age_days or 0)
    head_from = max(1, int(head_start_page or 1))

    out = ListScanResult(board_fid=numeric_fid, last_list_page=cursor)
    seen: set[int] = set()
    unit_key = pol.key
    name = board_name or pol.name
    page1_tids: frozenset[int] | None = None

    def _emit(msg: str) -> None:
        if on_log:
            on_log(msg)
        log.info("%s", msg)

    quota_label = f"本轮 {harvest_quota} 页 · 跨轮续扫至板底"
    head_stop_label = f"连续 {head_known_need} 页全已知即停"

    if not scan_head:
        out.head_skipped = True
        _emit(
            f"列表深扫 · 本轮跳过首页捕新 · "
            f"自游标 P{cursor or '—'} · {quota_label}"
        )
    elif not deep_scan:
        _emit(
            f"手动扫新帖 · 自 P{head_from}（上限 {head_cap}）· "
            f"{head_stop_label} · 本轮不深扫"
        )
    elif cursor >= 2:
        _emit(
            f"列表 · 首页捕新自 P{head_from}（上限 {head_cap}）· "
            f"{head_stop_label} · 随后深扫游标 P{cursor} · {quota_label}"
        )
    else:
        _emit(
            f"列表 · 首页捕新自 P{head_from}（上限 {head_cap}）· "
            f"{head_stop_label} · 深扫 {quota_label}"
        )

    # —— 1) 首页捕新（手动扫新帖 / 兼容旧混合路径）——
    if scan_head:
        page = head_from
        pages_read_in_head = 0
        known_streak = 0
        while pages_read_in_head < head_cap and page <= page_limit:
            if THROTTLE.should_stop():
                out.head_incomplete = True
                out.head_progress_page = page
                return out

            fetched = await _fetch_list_page(
                fetcher,
                board_fid=pol.key,
                page=page,
                root=root,
                pol=pol,
            )
            if fetched.login_required:
                out.login_required = True
                out.errors.append(fetched.error)
                out.head_incomplete = True
                out.head_progress_page = page
                _emit(f"第 {page} 页需登录 · 停板，请补 Cookie")
                return out
            if not fetched.ok:
                out.fetch_failures += 1
                out.errors.append(fetched.error or f"page={page} fetch failed")
                out.head_incomplete = True
                out.head_progress_page = page
                _emit(f"首页 P{page} 读取失败 · {fetched.error or 'unknown'} · 下轮自本页续扫")
                break

            if fetched.empty_list:
                out.pages_head.append(page)
                if page == 1:
                    out.list_exhausted = True
                    out.last_list_page = 1
                    out.head_completed = True
                    _emit("第 1 页无主题 · 列表可能到底；扫新帖视为完成")
                    await THROTTLE.sleep()
                    return out
                out.head_completed = True
                _emit(f"首页 P{page} 无主题 · 扫新帖完成")
                await THROTTLE.sleep()
                break

            tids = _tid_set(fetched.batch)
            if page == 1:
                page1_tids = tids

            out.pages_head.append(page)
            pages_read_in_head += 1
            upd_before = out.board_updated
            enq, young_skip = _enqueue_batch(
                out,
                fetched.batch,
                seen=seen,
                board_fid=unit_key,
                board_name=name,
                persist_enqueue=persist_enqueue,
                min_thread_age_days=min_age,
            )
            page_upd = out.board_updated - upd_before
            # 未满龄跳过不算「全已知」，避免板 141 首页因年轻帖早停
            if enq == 0 and young_skip == 0:
                known_streak += 1
            elif enq > 0:
                known_streak = 0
            _emit(
                f"首页捕新 P{page} · {len(fetched.batch)} 帖 · 新入队 {enq}（不计配额）"
                + (f" · 改板块 {page_upd}" if page_upd else "")
                + (f" · 未满龄跳过 {young_skip}" if young_skip else "")
                + (
                    f" · 全已知连续 {known_streak}/{head_known_need}"
                    if enq == 0 and young_skip == 0
                    else ""
                )
            )
            await THROTTLE.sleep()
            if known_streak >= head_known_need:
                out.head_completed = True
                _emit(
                    f"扫新帖完成 · 连续 {known_streak} 页所见均已入库"
                    + (" · 本轮结束" if not deep_scan else " · 随后深扫")
                )
                break
            page += 1
        else:
            if not out.head_completed and pages_read_in_head >= head_cap:
                out.head_incomplete = True
                out.head_progress_page = page
                _emit(
                    f"首页捕新触及上限 {head_cap} 页仍有新帖 · "
                    f"下轮自 P{page} 续扫"
                )

    if not deep_scan:
        if out.deferred_young:
            _emit(f"未满龄跳过入队 {out.deferred_young} 帖（满 {min_age} 天后再扫才入队）")
        return out

    # —— 2) 深扫：每轮 harvest_quota 页，跨轮续扫至空页/内容重复 ——
    resume = counted_resume_page(cursor)
    head_last = max(out.pages_head) if out.pages_head else 0
    deep_start = resume
    # 本轮已做首页捕新时，深扫从捕新之后继续，避免与首页重复
    if scan_head and head_last >= 1:
        deep_start = max(resume, head_last + 1)

    out.harvest_start_page = deep_start
    harvested = 0
    page = deep_start
    known_streak = 0
    prev_tids: frozenset[int] | None = None

    while page <= page_limit:
        if harvested >= harvest_quota:
            break
        if THROTTLE.should_stop():
            break

        fetched = await _fetch_list_page(
            fetcher,
            board_fid=pol.key,
            page=page,
            root=root,
            pol=pol,
        )
        if fetched.login_required:
            out.login_required = True
            out.errors.append(fetched.error)
            _emit(f"第 {page} 页需登录 · 停板")
            break
        if not fetched.ok:
            out.fetch_failures += 1
            out.errors.append(fetched.error or f"page={page}")
            _emit(
                f"第 {page} 页读取失败 · 本轮深扫暂停，游标保持 P{out.last_list_page or cursor}"
            )
            break

        if fetched.empty_list:
            out.list_exhausted = True
            out.last_list_page = page
            _emit(f"列表到底 · 第 {page} 页无主题，下轮从头计数")
            break

        tids = _tid_set(fetched.batch)

        # Discuz 超页：内容与上一页完全相同 → 到头
        if prev_tids is not None and tids and tids == prev_tids:
            out.list_exhausted = True
            out.last_list_page = max(0, page - 1)
            _emit(
                f"列表到底 · P{page} 与 P{page - 1} 主题完全重复（已到翻页尽头）· "
                f"游标 P{out.last_list_page}"
            )
            break

        # Discuz threadmaxpages：超限页夹回第 1 页内容
        if page1_tids and page > 1 and tids and tids == page1_tids:
            out.list_exhausted = True
            out.last_list_page = max(0, page - 1)
            _emit(
                f"列表到底 · P{page} 内容与第 1 页重复（站点页码上限夹回）· "
                f"游标 P{out.last_list_page}"
            )
            break

        out.pages_scanned.append(page)
        out.last_list_page = page
        harvested += 1
        prev_tids = tids
        upd_before = out.board_updated
        enq, young_skip = _enqueue_batch(
            out,
            fetched.batch,
            seen=seen,
            board_fid=unit_key,
            board_name=name,
            persist_enqueue=persist_enqueue,
            min_thread_age_days=min_age,
        )
        page_upd = out.board_updated - upd_before
        if enq == 0 and young_skip == 0:
            known_streak += 1
        elif enq > 0:
            known_streak = 0
        progress = f"{harvested}/{harvest_quota}"
        _emit(
            f"深扫 P{page} · {len(fetched.batch)} 帖 · 新入队 {enq}"
            + (f" · 改板块 {page_upd}" if page_upd else "")
            + f" · {progress}"
            + (f" · 未满龄跳过 {young_skip}" if young_skip else "")
            + (f" · 全已知连续 {known_streak}" if enq == 0 and young_skip == 0 else "")
        )
        await THROTTLE.sleep()
        page += 1

    if out.list_exhausted:
        pass
    elif harvested >= harvest_quota and out.pages_scanned:
        _emit(
            f"本批深扫配额已满 · P{out.harvest_start_page}~P{out.last_list_page} "
            f"共 {harvested} 页 · 合计新入队 {out.enqueued}"
            + (f" · 改板块 {out.board_updated}" if out.board_updated else "")
            + f" · 游标 P{out.last_list_page}"
        )
    elif page > page_limit:
        _emit(f"已达翻页上限 P{page_limit} · 游标停在 P{out.last_list_page}")

    if out.deferred_young:
        _emit(f"未满龄跳过入队 {out.deferred_young} 帖（满 {min_age} 天后再扫才入队）")

    return out
