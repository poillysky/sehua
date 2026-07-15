"""拓扑「扫列表」：第 1 页每轮必读（不计配额）→ 从上次结束页起按配置页数计数读取。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

from crawler.fetcher import Fetcher
from crawler.list_urls import list_url_for_board, resolve_page_cap, site_root
from crawler.parser import ThreadBrief, is_valid_forum_list, parse_forum_list
from crawler.session import SessionManager
from crawler.throttle import THROTTLE
from db.connection import connect
from db.queue import enqueue_thread
from parsers.boards import get_board_policy
from parsers.thread_gates import is_thread_login_required

log = logging.getLogger(__name__)

LogFn = Callable[[str], None]


@dataclass
class ListScanResult:
    board_fid: int
    pages_scanned: list[int] = field(default_factory=list)  # 计入配额的页
    pages_head: list[int] = field(default_factory=list)  # 第 1 页等不计配额
    pages_skipped: list[int] = field(default_factory=list)  # 兼容旧字段
    threads: list[ThreadBrief] = field(default_factory=list)
    enqueued: int = 0
    last_list_page: int = 0  # 计数阶段最后一页（游标）
    harvest_start_page: int = 0
    list_exhausted: bool = False
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
    min_thread_age_days: int,
) -> _PageFetch:
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
        min_thread_age_days=min_thread_age_days,
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
) -> int:
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
                if enqueue_thread(
                    conn,
                    url=t.url,
                    board_fid=board_fid,
                    board_name=board_name,
                    title=t.title,
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
            out.threads.append(t)
    return page_enqueued


async def scan_board_list(
    fetcher: Fetcher,
    *,
    board_fid: int,
    pages_per_board: int = 15,
    max_list_pages: int = 0,
    entry_url: str = "",
    last_list_page: int = 0,
    board_name: str = "",
    persist_enqueue: bool = True,
    on_log: Optional[LogFn] = None,
) -> ListScanResult:
    """扫列表并入队。

    规则：
    1. 每轮单独读第 1 页，不计入 pages_per_board 配额（及时发现首页新帖）。
    2. 计数扫描从「上次结束页」开头重读（含该页，避免漏帖）；无游标时从第 2 页起。
       例：上次停在第 5 页 → 本次计数自第 5 页开头，而非第 6 页。
    3. 计数阶段连续读取 pages_per_board 页；空页视为到底，游标由调用方复位。
    """
    pol = get_board_policy(board_fid)
    root = site_root(entry_url)
    harvest_quota = resolve_page_cap(pages_per_board, max_list_pages)
    page_limit = _safety_cap(max_list_pages)
    cursor = max(0, int(last_list_page or 0))
    # 含结束页：游标=5 → deep_start=5（绝不 +1，避免漏该页）
    deep_start = counted_resume_page(cursor)

    out = ListScanResult(board_fid=board_fid, last_list_page=cursor)
    seen: set[int] = set()
    name = board_name or pol.name

    def _emit(msg: str) -> None:
        if on_log:
            on_log(msg)
        log.info("%s", msg)

    if cursor >= 2:
        _emit(
            f"列表续扫 · 第1页单独读(不计配额) · "
            f"计数自第 {deep_start} 页开头重读（避漏）· 共 {harvest_quota} 页"
        )
    else:
        _emit(
            f"列表开扫 · 第1页单独读(不计配额) · "
            f"计数自第 {deep_start} 页起共 {harvest_quota} 页"
        )

    # —— 1) 第 1 页：必读，不计配额 ——
    if THROTTLE.should_stop():
        return out

    head = await _fetch_list_page(
        fetcher,
        board_fid=board_fid,
        page=1,
        root=root,
        pol=pol,
        min_thread_age_days=pol.min_thread_age_days,
    )
    if head.login_required:
        out.login_required = True
        out.errors.append(head.error)
        _emit("第 1 页需登录 · 停板，请补 Cookie")
        return out
    if not head.ok:
        out.fetch_failures += 1
        out.errors.append(head.error or "page=1 fetch failed")
        _emit(f"第 1 页读取失败 · {head.error or 'unknown'} · 仍继续计数扫描")
    elif head.empty_list:
        out.list_exhausted = True
        out.last_list_page = 1
        out.pages_head.append(1)
        _emit("第 1 页无主题 · 列表可能到底，下轮游标复位")
        await THROTTLE.sleep()
        return out
    else:
        out.pages_head.append(1)
        enq = _enqueue_batch(
            out,
            head.batch,
            seen=seen,
            board_fid=board_fid,
            board_name=name,
            persist_enqueue=persist_enqueue,
        )
        _emit(f"第 1 页 · {len(head.batch)} 帖 · 新入队 {enq}（不计配额）")
        await THROTTLE.sleep()

    # —— 2) 从上次结束页起计数读取 ——
    out.harvest_start_page = deep_start
    harvested = 0
    page = deep_start

    while harvested < harvest_quota and page <= page_limit:
        if THROTTLE.should_stop():
            break

        fetched = await _fetch_list_page(
            fetcher,
            board_fid=board_fid,
            page=page,
            root=root,
            pol=pol,
            min_thread_age_days=pol.min_thread_age_days,
        )
        if fetched.login_required:
            out.login_required = True
            out.errors.append(fetched.error)
            _emit(f"第 {page} 页需登录 · 停板")
            break
        if not fetched.ok:
            out.fetch_failures += 1
            out.errors.append(fetched.error or f"page={page}")
            _emit(f"第 {page} 页读取失败 · 跳过并计入配额进度")
            out.pages_scanned.append(page)
            out.last_list_page = page
            harvested += 1
            await THROTTLE.sleep()
            page += 1
            continue

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
        )
        _emit(
            f"计数 P{page} · {len(fetched.batch)} 帖 · 新入队 {enq} · "
            f"{harvested}/{harvest_quota}"
        )
        await THROTTLE.sleep()
        page += 1

    if harvested >= harvest_quota and out.pages_scanned:
        _emit(
            f"本批计数配额已满 · P{out.harvest_start_page}~P{out.last_list_page} "
            f"共 {harvested} 页 · 含首页新入队合计 {out.enqueued} · 游标 P{out.last_list_page}"
        )
    elif page > page_limit:
        _emit(f"已达翻页上限 P{page_limit} · 游标停在 P{out.last_list_page}")

    return out
