"""拓扑「扫列表」：每日一次首页捕新 + 当天其余轮次仅深扫。

策略:
1. 每天首次：从首页（或未完成进度页）起扫新帖，直到某一页「所见均已入库」→
   标记今日首页捕新完成；当天后续循环不再读第 1 页。
2. 深扫：始终从列表游标（含结束页重叠）向更旧页推进。
3. 深扫：按配额向更旧页推进；整页已入库也继续往后扫（不因「全已知」卡在同一游标空转）。
4. 龄期板（如 141）：未满龄帖带 retry_after 入队，不挡游标。
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
from db.queue import enqueue_thread
from parsers.boards import get_board_policy
from parsers.list_dates import is_thread_old_enough
from parsers.thread_gates import is_thread_login_required

log = logging.getLogger(__name__)

LogFn = Callable[[str], None]

# 深扫连续「全已知」页数达到该值则早停（可配置覆盖）
DEFAULT_KNOWN_STOP_PAGES = 2
# 每日首页捕新安全上限（页）；正常以「扫到全已知页」结束
DEFAULT_HEAD_PAGES = 50


@dataclass
class ListScanResult:
    board_fid: int
    pages_scanned: list[int] = field(default_factory=list)  # 计入配额的页
    pages_head: list[int] = field(default_factory=list)  # 首页捕新（不计配额）
    pages_skipped: list[int] = field(default_factory=list)  # 兼容旧字段
    threads: list[ThreadBrief] = field(default_factory=list)
    enqueued: int = 0
    deferred_young: int = 0
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


def _safety_cap(max_list_pages: int) -> int:
    safety = 300
    global_cap = int(max_list_pages or 0)
    if global_cap <= 0:
        return safety
    return min(global_cap, safety)


def counted_resume_page(last_list_page: int) -> int:
    """计数阶段起点：上次结束页（含），避免漏帖；无游标则从第 2 页。

    例：last=5 → 返回 5（从第五页头读取，不是 6）。
    """
    cursor = max(0, int(last_list_page or 0))
    if cursor >= 2:
        return cursor
    return 2


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
    board_fid: int,
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
    board_fid: int,
    board_name: str,
    persist_enqueue: bool,
    min_thread_age_days: int = 0,
) -> int:
    """入队；返回本页新插入数。未满龄帖带 retry_after。"""
    page_enqueued = 0
    if not batch:
        return 0
    if persist_enqueue:
        conn = connect()
        try:
            for t in batch:
                if t.tid in seen:
                    continue
                seen.add(t.tid)
                out.threads.append(t)
                retry_after = None
                if min_thread_age_days > 0 and not is_thread_old_enough(
                    t.posted_at,  # type: ignore[arg-type]
                    min_age_days=min_thread_age_days,
                ):
                    retry_after = age_retry_after(t.posted_at, min_thread_age_days)  # type: ignore[arg-type]
                if enqueue_thread(
                    conn,
                    url=t.url,
                    board_fid=board_fid,
                    board_name=board_name,
                    title=t.title,
                    retry_after=retry_after,
                ):
                    out.enqueued += 1
                    page_enqueued += 1
                    if retry_after is not None:
                        out.deferred_young += 1
        finally:
            conn.close()
    else:
        for t in batch:
            if t.tid in seen:
                continue
            seen.add(t.tid)
            out.threads.append(t)
            if min_thread_age_days > 0 and not is_thread_old_enough(
                t.posted_at,  # type: ignore[arg-type]
                min_age_days=min_thread_age_days,
            ):
                out.deferred_young += 1
    return page_enqueued


async def scan_board_list(
    fetcher: Fetcher,
    *,
    board_fid: int,
    pages_per_board: int = 15,
    max_list_pages: int = 0,
    head_pages: int = DEFAULT_HEAD_PAGES,
    known_stop_pages: int = DEFAULT_KNOWN_STOP_PAGES,
    scan_head: bool = True,
    head_start_page: int = 1,
    entry_url: str = "",
    last_list_page: int = 0,
    board_name: str = "",
    persist_enqueue: bool = True,
    on_log: Optional[LogFn] = None,
) -> ListScanResult:
    """扫列表并入队。

    规则：
    1. scan_head=True：从 head_start_page 起捕新，直到某页新入队为 0（全已知）或触顶。
    2. scan_head=False：跳过首页，仅深扫（今日已完成捕新后的循环）。
    3. 深扫从列表游标（与首页已读错开）起读 pages_per_board 页。
    4. 整页已入库仍继续向后翻，用满本轮配额；游标停在本轮最后一页。
       （旧逻辑「全已知早停」会把游标卡在同一页反复空转，已取消。）
    5. 列表页失败不推进游标。
    """
    pol = get_board_policy(board_fid)
    root = site_root(entry_url)
    harvest_quota = resolve_page_cap(pages_per_board, max_list_pages)
    page_limit = _safety_cap(max_list_pages)
    cursor = max(0, int(last_list_page or 0))
    head_cap = max(1, int(head_pages or DEFAULT_HEAD_PAGES))
    # known_stop_pages 保留配置兼容；0/旧「早停」不再中断深扫（避免卡游标）
    _ = int(known_stop_pages or 0)
    min_age = int(pol.min_thread_age_days or 0)
    head_from = max(1, int(head_start_page or 1))

    out = ListScanResult(board_fid=board_fid, last_list_page=cursor)
    seen: set[int] = set()
    name = board_name or pol.name

    def _emit(msg: str) -> None:
        if on_log:
            on_log(msg)
        log.info("%s", msg)

    if not scan_head:
        out.head_skipped = True
        _emit(
            f"列表深扫 · 今日首页捕新已完成，本轮跳过第1页 · "
            f"自游标 P{cursor or '—'} 配额 {harvest_quota} 页（全已知也继续后扫）"
        )
    elif cursor >= 2:
        _emit(
            f"列表 · 每日首页捕新自 P{head_from}（安全上限 {head_cap}）· "
            f"扫到全已知页即停 · 随后深扫游标 P{cursor} · 配额 {harvest_quota}"
        )
    else:
        _emit(
            f"列表 · 每日首页捕新自 P{head_from}（安全上限 {head_cap}）· "
            f"扫到全已知页即停 · 深扫配额 {harvest_quota}"
        )

    # —— 1) 每日一次首页捕新 ——
    if scan_head:
        page = head_from
        pages_read_in_head = 0
        while pages_read_in_head < head_cap and page <= page_limit:
            if THROTTLE.should_stop():
                out.head_incomplete = True
                out.head_progress_page = page
                return out

            fetched = await _fetch_list_page(
                fetcher,
                board_fid=board_fid,
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
                    _emit("第 1 页无主题 · 列表可能到底；今日首页捕新视为完成")
                    await THROTTLE.sleep()
                    return out
                out.head_completed = True
                _emit(f"首页 P{page} 无主题 · 今日捕新完成，后续轮次仅深扫")
                await THROTTLE.sleep()
                break

            out.pages_head.append(page)
            pages_read_in_head += 1
            enq = _enqueue_batch(
                out,
                fetched.batch,
                seen=seen,
                board_fid=board_fid,
                board_name=name,
                persist_enqueue=persist_enqueue,
                min_thread_age_days=min_age,
            )
            _emit(
                f"首页捕新 P{page} · {len(fetched.batch)} 帖 · 新入队 {enq}（不计配额）"
            )
            await THROTTLE.sleep()
            if enq == 0:
                out.head_completed = True
                _emit(
                    f"首页捕新完成 · P{page} 所见均已入库 · "
                    f"今日不再扫新帖，后续循环只深扫"
                )
                break
            page += 1
        else:
            if not out.head_completed and pages_read_in_head >= head_cap:
                out.head_incomplete = True
                out.head_progress_page = page
                _emit(
                    f"首页捕新触及安全上限 {head_cap} 页仍有新帖 · "
                    f"下轮自 P{page} 续扫"
                )

    # —— 2) 深扫 ——
    resume = counted_resume_page(cursor)
    head_last = max(out.pages_head) if out.pages_head else 0
    deep_start = resume
    if scan_head and head_last >= 2:
        deep_start = max(resume, head_last + 1)

    out.harvest_start_page = deep_start
    harvested = 0
    page = deep_start
    known_streak = 0

    while harvested < harvest_quota and page <= page_limit:
        if THROTTLE.should_stop():
            break

        fetched = await _fetch_list_page(
            fetcher,
            board_fid=board_fid,
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

        out.pages_scanned.append(page)
        out.last_list_page = page
        harvested += 1
        enq = _enqueue_batch(
            out,
            fetched.batch,
            seen=seen,
            board_fid=board_fid,
            board_name=name,
            persist_enqueue=persist_enqueue,
            min_thread_age_days=min_age,
        )
        if enq == 0:
            known_streak += 1
        else:
            known_streak = 0
        _emit(
            f"深扫 P{page} · {len(fetched.batch)} 帖 · 新入队 {enq} · "
            f"{harvested}/{harvest_quota}"
            + (f" · 全已知连续 {known_streak}" if enq == 0 else "")
        )
        await THROTTLE.sleep()
        # 全已知也继续 page+1，用满配额，避免卡在同一游标反复早停空转
        page += 1

    if harvested >= harvest_quota and out.pages_scanned:
        _emit(
            f"本批深扫配额已满 · P{out.harvest_start_page}~P{out.last_list_page} "
            f"共 {harvested} 页 · 合计新入队 {out.enqueued} · 游标 P{out.last_list_page}"
        )
    elif page > page_limit:
        _emit(f"已达翻页上限 P{page_limit} · 游标停在 P{out.last_list_page}")

    if out.deferred_young:
        _emit(f"未满龄延期入队 {out.deferred_young} 帖（到期自动可抓）")

    return out
