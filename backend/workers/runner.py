"""拓扑调度：连续循环 · 发帖时间序扫列表 · 持久队列 · AutoThrottle。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from crawler.list_urls import list_url_for_board, site_root
from crawler.throttle import THROTTLE
from db.connection import connect
from db.forum_configs import (
    SITE_CRAWLER_FORUM_ID,
    advance_active_board_fid,
    get_active_forum_id,
    get_board_head_progress,
    get_board_list_cursor,
    is_board_head_done_today,
    load_forum_configs_map,
    resolve_enabled_board_fids,
    resolve_manual_head_pages,
    save_forum_config,
    set_board_head_catchup_state,
    set_board_list_cursor,
)
from db.migrate import run_migrations
from db.queue import (
    MAX_THREAD_RETRIES,
    QUEUE_LIST_BACKPRESSURE,
    count_pending,
    dedupe_pending_by_tid,
    fetch_pending_abnormal,
    fetch_pending_threads,
    mark_pending_retry,
    mark_thread_done,
    mark_thread_skipped,
    tid_from_url,
)
from db.settings_store import get_setting
from parsers.boards import BOARD_POLICIES, get_board_policy, queue_board_keys
from workers.list_scan import scan_board_list
from workers.pipeline import process_thread
from workers.session_factory import (
    entry_urls_from_config,
    fetcher_from_config,
    session_from_config,
)

log = logging.getLogger(__name__)

_STATE: dict[str, Any] = {
    "running": False,
    "looping": False,
    "loop_kind": None,
    "phase": "idle",
    "last_result": None,
    "last_started_at": None,
    "last_finished_at": None,
    "activity": [],
    "throttle": {},
    "queue": {},
}

_loop_task: asyncio.Task | None = None
_round_task: asyncio.Task | None = None


def crawl_status() -> dict[str, Any]:
    out = dict(_STATE)
    out["throttle"] = THROTTLE.status()
    out["stopping"] = bool(THROTTLE.should_stop() and _STATE.get("running"))
    if out.get("looping") and not out.get("loop_kind"):
        out["loop_kind"] = "deep"
    return out


def try_begin_exclusive(phase: str = "recrawl") -> dict[str, Any]:
    """占用 running，供已入库重爬等手工任务。连续调度或正在抓取时拒绝。"""
    if _STATE.get("looping"):
        return {"ok": False, "reason": "loop_running", "error": "连续调度进行中，请先关闭后再立即重爬"}
    if _STATE.get("running"):
        return {"ok": False, "reason": "busy", "error": "爬虫正在执行，请稍后再重爬"}
    _STATE["running"] = True
    _STATE["phase"] = phase
    _STATE["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return {"ok": True}


def end_exclusive() -> None:
    """释放 try_begin_exclusive 占用。连续调度中不改 looping。"""
    if _STATE.get("looping"):
        return
    _STATE["running"] = False
    _STATE["loop_inner"] = False
    _STATE["phase"] = "idle"
    _STATE["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")


def request_stop() -> None:
    THROTTLE.request_stop()
    _STATE["looping"] = False
    _STATE["phase"] = "stopping" if _STATE.get("running") else _STATE.get("phase") or "idle"


def _log_activity(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    item = {"t": ts, "msg": msg}
    activity = list(_STATE.get("activity") or [])
    activity.insert(0, item)
    _STATE["activity"] = activity[:120]
    log.info("%s", msg)


def _ensure_queue_schema() -> None:
    try:
        run_migrations(only={"015_crawl_queue_retry.sql"})
    except Exception as exc:
        log.warning("queue migration: %s", exc)


async def run_crawl_once(
    *,
    forum_id: str = SITE_CRAWLER_FORUM_ID,
    max_threads: Optional[int] = None,
    persist: bool = True,
    scan_list: bool = True,
    scan_head: bool | None = None,
    deep_scan: bool = True,
    head_pages_override: int | None = None,
    board_fid_override: str | int | None = None,
    from_loop: bool = False,
    require_enabled: bool = True,
    queue_kind: str | None = None,
    hold_lock: bool = False,
) -> dict[str, Any]:
    """执行拓扑一轮：选板→进站→扫列表入队→取待抓→抓帖入库。

    - 手动「立即爬取」：from_loop=False；连续调度启用时拒绝；默认仅深扫当前板。
    - 手动「扫新帖」：scan_head=True, deep_scan=False；可由 run_scan_head_once 按启用队列逐板调用。
    - 连续循环：scan_head=False, deep_scan=True, from_loop=True；当前板 list_exhausted 后切下一启用板。
    - queue_kind=abnormal|soft_ad：只在该队列内重爬，成功才出队，不扫列表。
    - hold_lock=True：调用方已占用 running，本函数不抢锁/不释放。
    """
    kind = (queue_kind or "").strip().lower() or None
    if kind not in {None, "abnormal", "soft_ad"}:
        return {"ok": False, "skipped": True, "reason": "bad_queue_kind", "error": "未知队列类型"}
    if kind:
        scan_list = False

    if hold_lock:
        if not _STATE.get("running"):
            return {
                "ok": False,
                "skipped": True,
                "reason": "no_lock",
                "error": "内部调用缺少运行锁",
            }
        _ensure_queue_schema()
        _STATE["loop_inner"] = True
        _STATE["phase"] = "switch"
    else:
        if _STATE.get("looping") and not from_loop:
            return {
                "ok": False,
                "skipped": True,
                "reason": "loop_running",
                "error": "连续调度进行中，请先关闭后再操作",
            }
        if _STATE.get("running") and not _STATE.get("looping"):
            return {"ok": False, "skipped": True, "reason": "already_running", **crawl_status()}
        if _STATE.get("running") and _STATE.get("loop_inner"):
            return {"ok": False, "skipped": True, "reason": "already_running"}

        _ensure_queue_schema()
        _STATE["running"] = True
        _STATE["loop_inner"] = True
        _STATE["phase"] = "switch"
        _STATE["last_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        global _round_task
        _round_task = asyncio.current_task()
        # 手动开跑清停止标志；连续循环内保留（由 loop/start 清理）
        if not from_loop:
            THROTTLE.clear_stop()

    result: dict[str, Any] = {
        "ok": True,
        "forum_id": forum_id,
        "enabled": False,
        "board_fid": None,
        "discovered": 0,
        "enqueued": 0,
        "board_updated": 0,
        "crawled": 0,
        "imports": 0,
        "stubs": 0,
        "retries": 0,
        "skipped": 0,
        "failed": 0,
        "soft_browser_retried": 0,
        "fetch_failures": 0,
        "cooldowns": 0,
        "pages_scanned": [],
        "verdicts": {},
        "list_sort": "dateline",
        "queue_kind": kind or "ready",
    }

    session = None
    try:
        conn = connect()
        try:
            active = get_active_forum_id(conn)
            configs = load_forum_configs_map(conn)
            cfg = configs.get(forum_id) or {}
            proxy = get_setting(conn, "web_crawler_proxy", "")
        finally:
            conn.close()

        enabled = bool(cfg.get("web_crawler_enabled"))
        result["enabled"] = enabled
        if require_enabled and not enabled:
            _log_activity("爬虫开关关闭 · 不调度")
            result["skipped"] = True
            result["reason"] = "disabled"
            return result
        if active != forum_id:
            _log_activity(f"当前启用论坛={active} · 跳过 {forum_id}")
            result["skipped"] = True
            result["reason"] = "not_active_forum"
            return result

        _STATE["phase"] = "scheduler"
        delay = float(cfg.get("web_crawler_request_delay") or 2.0)
        fail_threshold = int(cfg.get("web_crawler_fetch_failure_threshold") or 5)
        cool_secs = int(cfg.get("web_crawler_fetch_cooldown_seconds") or 45)
        max_cools = int(cfg.get("web_crawler_fetch_max_cooldowns") or 3)
        target = int(cfg.get("web_crawler_target_imports") or 0)
        THROTTLE.configure(
            base_delay=delay,
            max_delay=float(cfg.get("web_crawler_autothrottle_max_delay") or 60),
            window=int(cfg.get("web_crawler_autothrottle_window") or 20),
            failure_threshold=fail_threshold,
        )
        result["request_delay"] = delay
        result["target_imports"] = target
        _log_activity(
            f"调度 · 连续无间隔 · 基准延迟 {delay}s · AutoThrottle "
            f"窗{cfg.get('web_crawler_autothrottle_window')} "
            f"上限{cfg.get('web_crawler_autothrottle_max_delay')}s · 目标 {target or '不限'}"
        )

        _STATE["phase"] = "board_select"
        enabled = resolve_enabled_board_fids(cfg)
        result["enabled_board_fids"] = enabled
        if board_fid_override is not None:
            board_fid_s = str(board_fid_override).strip()
        else:
            board_fid_s = str(cfg.get("active_board_fid") or "").strip()
            if board_fid_s not in enabled and enabled:
                board_fid_s = enabled[0]
        if board_fid_s not in BOARD_POLICIES:
            result["ok"] = False
            result["error"] = f"工作子版 {board_fid_s} 不在白名单"
            _log_activity(result["error"])
            return result
        if enabled and board_fid_s not in enabled:
            result["ok"] = False
            result["error"] = f"工作子版 {board_fid_s} 未在启用队列中"
            _log_activity(result["error"])
            return result
        unit_key = board_fid_s
        pol = get_board_policy(unit_key)
        board_fid = int(pol.fid)
        queue_keys = queue_board_keys(unit_key)
        result["board_key"] = unit_key
        result["board_fid"] = board_fid
        result["board_typeid"] = pol.list_typeid
        result["board_name"] = pol.name
        queue_label = " → ".join(enabled[:8])
        if len(enabled) > 8:
            queue_label += f" …(+{len(enabled) - 8})"
        _log_activity(
            f"选板 · {pol.name}（{unit_key}）· 主链 {pol.primary_link}"
            + (f" · 满 {pol.min_thread_age_days} 天" if pol.min_thread_age_days else "")
            + f" · 启用队列 {len(enabled)} 子版 [{queue_label}]"
            + " · 发帖时间序"
        )

        _STATE["phase"] = "session"
        session = session_from_config(cfg, proxy=proxy)
        entries = entry_urls_from_config(cfg)
        await session.bootstrap(entry_urls=entries)
        start = session.active_entry_url or (entries[0] if entries else "")
        result["proxy_configured"] = bool((proxy or "").strip())
        result["entry_url"] = start
        _log_activity(f"进站就绪 · {start}" + (f" · 代理 {proxy}" if proxy else ""))

        fetcher = fetcher_from_config(session, cfg, proxy=proxy)
        root = site_root(start)

        if scan_list:
            # 队列积压：超过阈值则本轮不读列表，先清空/消化待抓
            pre_q = {}
            try:
                qconn = connect()
                try:
                    pre_q = count_pending(qconn, board_fid=queue_keys)
                finally:
                    qconn.close()
            except Exception as qexc:
                log.warning("pre-scan queue count: %s", qexc)
            # 只计正常可抓队列，异常/软文不计入背压
            pending_ready = int(pre_q.get("ready") or 0)
            result["queue_before_list"] = pending_ready
            if pending_ready >= QUEUE_LIST_BACKPRESSURE:
                _log_activity(
                    f"正常待抓已有 {pending_ready}（≥{QUEUE_LIST_BACKPRESSURE}）· "
                    f"本轮跳过列表读取，先清空正常队列（异常/软文不计）"
                )
                result["list_skipped"] = True
                result["reason"] = "queue_backpressure"
            else:
                _STATE["phase"] = "list_scan"
                pages_per = int(cfg.get("web_crawler_list_pages_per_board") or 15)
                max_pages = int(cfg.get("web_crawler_max_list_pages") or 0)
                known_stop = int(cfg.get("web_crawler_list_known_stop_pages") or 2)
                list_cursor = get_board_list_cursor(cfg, unit_key)
                # 供状态接口在本轮扫完前也能读到推进中的游标
                live_cursors = dict(cfg.get("board_list_cursors") or {})
                _STATE["board_list_cursors"] = live_cursors

                def _on_list_cursor(key: str, page: int) -> None:
                    live = dict(_STATE.get("board_list_cursors") or {})
                    live[str(key)] = max(0, int(page or 0))
                    _STATE["board_list_cursors"] = live
                    try:
                        cconn = connect()
                        try:
                            set_board_list_cursor(cconn, forum_id, key, page, reset=False)
                        finally:
                            cconn.close()
                    except Exception as cexc:
                        log.warning("live cursor persist %s P%s: %s", key, page, cexc)

                if scan_head is None:
                    do_head = not is_board_head_done_today(cfg, unit_key)
                else:
                    do_head = bool(scan_head)
                do_deep = bool(deep_scan)
                if head_pages_override is not None:
                    head_pages = max(1, int(head_pages_override))
                elif do_head and not do_deep:
                    head_pages = resolve_manual_head_pages(cfg, unit_key)
                else:
                    head_pages = int(cfg.get("web_crawler_list_head_pages") or 50)
                head_start = get_board_head_progress(cfg, unit_key) if do_head else 1
                scan = await scan_board_list(
                    fetcher,
                    board_fid=unit_key,
                    pages_per_board=pages_per,
                    max_list_pages=max_pages,
                    head_pages=head_pages,
                    known_stop_pages=known_stop,
                    scan_head=do_head,
                    deep_scan=do_deep,
                    head_start_page=head_start,
                    entry_url=start,
                    last_list_page=list_cursor,
                    board_name=pol.name,
                    persist_enqueue=True,
                    on_log=_log_activity,
                    on_cursor=_on_list_cursor,
                )
                result["pages_scanned"] = scan.pages_scanned
                result["pages_head"] = list(getattr(scan, "pages_head", None) or [])
                result["pages_skipped"] = list(scan.pages_skipped)
                result["discovered"] = len(scan.threads)
                result["enqueued"] = scan.enqueued
                result["board_updated"] = int(getattr(scan, "board_updated", 0) or 0)
                result["list_cursor"] = scan.last_list_page
                result["harvest_start_page"] = scan.harvest_start_page
                result["deep_early_stop"] = bool(getattr(scan, "deep_early_stop", False))
                result["deferred_young"] = int(getattr(scan, "deferred_young", 0) or 0)
                result["head_skipped"] = bool(getattr(scan, "head_skipped", False))
                result["head_completed"] = bool(getattr(scan, "head_completed", False))
                result["scan_head"] = do_head
                result["deep_scan"] = do_deep
                result["fetch_failures"] += scan.fetch_failures
                # 列表入队后立刻刷新队列计数，供状态页轮询
                try:
                    qconn = connect()
                    try:
                        _STATE["queue"] = count_pending(qconn, board_fid=queue_keys)
                    finally:
                        qconn.close()
                except Exception:
                    pass
                # 持久化游标：到底也不清空，仅手动「清除游标」才删；下次再扫该板从该页续判
                cursor_conn = connect()
                try:
                    set_board_list_cursor(
                        cursor_conn,
                        forum_id,
                        unit_key,
                        scan.last_list_page,
                        reset=False,
                    )
                    live = dict(_STATE.get("board_list_cursors") or {})
                    live[str(unit_key)] = max(0, int(scan.last_list_page or 0))
                    _STATE["board_list_cursors"] = live
                    if do_deep and scan.list_exhausted:
                        saved = advance_active_board_fid(
                            cursor_conn, forum_id, from_fid=unit_key
                        )
                        nxt = str(saved.get("active_board_fid") or "")
                        result["board_advanced"] = True
                        result["next_board_fid"] = nxt
                        _log_activity(
                            f"子版 {unit_key} 深扫到底 · 游标保留 P{scan.last_list_page} · "
                            f"下轮切换为 {nxt or '—'}"
                        )
                    if do_head and scan.head_completed:
                        if do_deep:
                            set_board_head_catchup_state(
                                cursor_conn,
                                forum_id,
                                unit_key,
                                done_today=True,
                            )
                        else:
                            set_board_head_catchup_state(
                                cursor_conn,
                                forum_id,
                                unit_key,
                                clear_progress=True,
                            )
                            _log_activity("本子版扫新帖结束 · 未写入每日捕新闸门")
                    elif do_head and scan.head_incomplete and scan.head_progress_page:
                        set_board_head_catchup_state(
                            cursor_conn,
                            forum_id,
                            unit_key,
                            progress_page=int(scan.head_progress_page),
                        )
                except Exception as cursor_exc:
                    log.warning("save list cursor / head catchup: %s", cursor_exc)
                finally:
                    cursor_conn.close()
                if scan.login_required:
                    _log_activity("列表需登录 · 停板，请补 Cookie")
                    result["reason"] = "list_login_required"
                    return result
                head_n = len(getattr(scan, "pages_head", None) or [])
                if scan.head_skipped:
                    head_label = "首页跳过"
                elif head_n:
                    head_label = f"首页捕新 {head_n} 页"
                else:
                    head_label = "首页未读"
                deep_n = len(scan.pages_scanned)
                if not do_deep:
                    deep_label = "深扫跳过"
                else:
                    deep_label = f"深扫 {deep_n} 页" + (
                        f"（自 P{scan.harvest_start_page}）"
                        if scan.harvest_start_page
                        else ""
                    )
                _log_activity(
                    f"扫列表(发帖时间) · {head_label} · {deep_label}"
                    + f" · 发现 {len(scan.threads)} · 新入队 {scan.enqueued}"
                    + (
                        f" · 改板块 {scan.board_updated}"
                        if getattr(scan, "board_updated", 0)
                        else ""
                    )
                    + (f" · 游标 P{scan.last_list_page}" if scan.last_list_page else "")
                )

        list_url = list_url_for_board(board_fid, 1, root=root, policy=pol)
        fetcher.set_referer(list_url)

        _STATE["phase"] = "thread_crawl"
        conn = connect()
        try:
            # .net/.org 等同 tid 双 URL 先合并，避免一轮里抓两次同一帖
            merged = dedupe_pending_by_tid(conn, board_fid=queue_keys)
            if merged:
                _log_activity(f"队列去重 · 合并同帖重复 URL {merged} 条")
            qstats = count_pending(conn, board_fid=queue_keys)
            _STATE["queue"] = qstats
            if kind in {"abnormal", "soft_ad"}:
                pending = fetch_pending_abnormal(conn, board_fid=queue_keys, limit=500)
            else:
                pending = fetch_pending_threads(conn, board_fid=queue_keys, limit=500)
        finally:
            conn.close()

        if kind in {"abnormal", "soft_ad"}:
            _log_activity(f"异常队列重爬 · {len(pending)} 条（含原软文；成功才出队）")
        else:
            deferred = int(qstats.get("deferred") or 0)
            workable = int(qstats.get("workable") or len(pending))
            _log_activity(
                f"待抓队列 · 可抓 {workable}（正常 {qstats.get('ready', 0)}）· "
                f"异常 {qstats.get('abnormal', 0)}"
                + (f" · 退避中 {deferred}" if deferred else "")
            )
            if not pending and int(result.get("discovered") or 0) > 0 and int(result.get("enqueued") or 0) == 0:
                if deferred > 0:
                    _log_activity(
                        f"本轮无可抓帖 · 列表所见均已入库，{deferred} 条退避中待到期自动重试"
                    )
                else:
                    _log_activity("本轮无可抓帖 · 列表所见均已入库，队列为空")

        consecutive_fail = 0
        cooldowns = 0
        seen_tids: set[int] = set()
        thread_cap = max_threads
        if thread_cap is None:
            cfg_cap = int(cfg.get("web_crawler_max_threads_per_run") or 0)
            thread_cap = cfg_cap if cfg_cap > 0 else None

        for idx, row in enumerate(pending):
            if THROTTLE.should_stop():
                result["reason"] = "stopped"
                break
            if thread_cap is not None and idx >= thread_cap:
                break
            if target > 0 and result["imports"] + result["stubs"] >= target:
                _log_activity(f"本批入库已达上限 {target} · 收工")
                result["reason"] = "target_reached"
                break

            if consecutive_fail >= fail_threshold:
                if cooldowns >= max_cools:
                    _log_activity(f"连续失败熔断（冷却已满 {max_cools} 次）")
                    result["reason"] = "cooldown_tripped"
                    break
                cooldowns += 1
                result["cooldowns"] = cooldowns
                _log_activity(
                    f"连续失败 ≥ {fail_threshold} · 冷却 {cool_secs}s（{cooldowns}/{max_cools}）"
                )
                _STATE["phase"] = "cooldown"
                await THROTTLE.sleep_for(cool_secs)
                if THROTTLE.should_stop():
                    result["reason"] = "stopped"
                    break
                consecutive_fail = 0
                _STATE["phase"] = "thread_crawl"

            tid = int(row.get("tid") or tid_from_url(row["url"]) or 0)
            if not tid:
                continue
            if tid in seen_tids:
                continue
            seen_tids.add(tid)
            title = str(row.get("thread_title") or "")
            thread_url = str(row["url"])
            stored_key = str(row.get("board_fid") or "").strip()
            stored_name = str(row.get("board_name") or "").strip()
            # 旧队列纯 fid：归到当前子版；新队列用子版 key
            if stored_key and ":" in stored_key:
                thread_key = stored_key
                thread_pol = get_board_policy(thread_key)
                thread_name = stored_name or thread_pol.name
            else:
                thread_key = unit_key
                thread_name = stored_name if (" · " in stored_name or "-" in stored_name) else pol.name

            try:
                await THROTTLE.sleep()
                if THROTTLE.should_stop():
                    result["reason"] = "stopped"
                    break
                outcome = await process_thread(
                    tid,
                    board_fid=thread_key,
                    board_name=thread_name,
                    session=session,
                    list_title=title,
                    persist=persist,
                    crawler_config=cfg,
                    fetcher=fetcher,
                )
                result["crawled"] += 1
                verdict = str(outcome.get("verdict") or "failed")
                result["verdicts"][verdict] = result["verdicts"].get(verdict, 0) + 1
                if outcome.get("soft_browser_retried"):
                    result["soft_browser_retried"] += 1

                log_label = str(outcome.get("verdict_label") or verdict)
                conn = connect()
                try:
                    if verdict == "import":
                        result["imports"] += 1
                        consecutive_fail = 0
                        THROTTLE.record_success()
                        mark_thread_done(conn, thread_url, outcome=str(outcome.get("outcome") or "import"))
                    elif verdict == "stub":
                        result["stubs"] += 1
                        consecutive_fail = 0
                        THROTTLE.record_success()
                        mark_thread_done(conn, thread_url, outcome=str(outcome.get("outcome") or "stub"))
                    elif verdict == "skipped":
                        result["skipped"] += 1
                        consecutive_fail = 0
                        THROTTLE.record_success()
                        mark_thread_skipped(conn, thread_url, str(outcome.get("outcome") or "skipped"))
                        # 无权伪标题等：清掉历史上错误占位，避免重爬后仍留在资源列表
                        try:
                            from db.repository import delete_stub_by_source_url

                            if delete_stub_by_source_url(conn, thread_url):
                                log_label = f"{log_label} · 已删占位"
                        except Exception:
                            pass
                    elif verdict == "retry" or "软文" in str(outcome.get("outcome") or ""):
                        result["retries"] += 1
                        consecutive_fail += 1
                        THROTTLE.record_failure()
                        prev_fails = int(row.get("fetch_fail_count") or 0)
                        err_msg = str(outcome.get("outcome") or "retry")
                        # 软文壳与其它失败统一进异常重试池，计数与耗尽规则一致
                        if prev_fails + 1 >= MAX_THREAD_RETRIES:
                            mark_thread_done(
                                conn,
                                thread_url,
                                outcome=f"重试{MAX_THREAD_RETRIES}次仍失败：{err_msg[:120]}",
                                status="failed",
                            )
                            result["failed"] += 1
                            log_label = f"重试耗尽出队 · {err_msg}"
                        else:
                            backoff = (
                                3600
                                if (
                                    outcome.get("soft_browser_retried")
                                    or "软文" in err_msg
                                    or "安全壳" in err_msg
                                )
                                else 900
                            )
                            mark_pending_retry(
                                conn,
                                thread_url,
                                err_msg,
                                backoff_seconds=backoff,
                            )
                    elif verdict == "need_attachments":
                        result["retries"] += 1
                        consecutive_fail += 1
                        THROTTLE.record_failure()
                        prev_fails = int(row.get("fetch_fail_count") or 0)
                        if prev_fails + 1 >= MAX_THREAD_RETRIES:
                            mark_thread_done(
                                conn,
                                thread_url,
                                outcome="重试耗尽：需下附件仍失败",
                                status="failed",
                            )
                            result["failed"] += 1
                            log_label = "重试耗尽出队 · 需下附件仍失败"
                        else:
                            mark_pending_retry(
                                conn, thread_url, "need_attachments", backoff_seconds=600
                            )
                    else:
                        result["failed"] += 1
                        consecutive_fail += 1
                        THROTTLE.record_failure()
                        mark_thread_done(
                            conn,
                            thread_url,
                            outcome=str(outcome.get("outcome") or "failed"),
                            status="failed",
                        )
                finally:
                    conn.close()

                _log_activity(
                    f"抓帖 tid={tid} · {log_label}"
                    + (" · 软文浏览器重读" if outcome.get("soft_browser_retried") else "")
                )
            except Exception as exc:
                consecutive_fail += 1
                result["failed"] += 1
                result["fetch_failures"] += 1
                THROTTLE.record_failure()
                try:
                    conn = connect()
                    try:
                        mark_pending_retry(conn, thread_url, str(exc)[:200], backoff_seconds=600)
                    finally:
                        conn.close()
                except Exception:
                    pass
                _log_activity(f"抓帖 tid={tid} 失败 · {exc}")

            if THROTTLE.should_stop():
                result["reason"] = "stopped"
                break

        _STATE["phase"] = "import"
        result["phase"] = "done"
        result["throttle"] = THROTTLE.status()
        try:
            conn = connect()
            try:
                _STATE["queue"] = count_pending(conn, board_fid=queue_keys)
            finally:
                conn.close()
        except Exception:
            pass
        if result.get("reason") == "stopped":
            _log_activity(
                f"本轮已手动停止 · 抓 {result['crawled']} · 入库 {result['imports']} · "
                f"未完成队列已保留"
            )
        else:
            _log_activity(
                f"本轮结束 · 入队 {result['enqueued']} · 抓 {result['crawled']} · "
                f"入库 {result['imports']}+占位 {result['stubs']} · 重试 {result['retries']}"
            )
        return result
    except asyncio.CancelledError:
        result["ok"] = False
        result["reason"] = "stopped"
        result["error"] = "cancelled"
        _log_activity("本轮任务已取消 · 会话清理中 · 未完成队列已保留")
        raise
    except Exception as exc:
        result["ok"] = False
        result["error"] = str(exc)
        _log_activity(f"本轮异常 · {exc}")
        log.exception("crawl round failed")
        return result
    finally:
        if session is not None:
            try:
                await session.close()
            except Exception:
                pass
        if hold_lock:
            # 调用方继续持有 running，不写 last_result / 不置 idle
            _STATE["loop_inner"] = False
            _STATE["throttle"] = THROTTLE.status()
        else:
            if _round_task is asyncio.current_task():
                _round_task = None
            _STATE["loop_inner"] = False
            if not _STATE.get("looping"):
                _STATE["running"] = False
                _STATE["phase"] = "idle"
            _STATE["last_finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _STATE["throttle"] = THROTTLE.status()
            _STATE["last_result"] = {
                k: result.get(k)
                for k in (
                    "ok",
                    "enabled",
                    "board_fid",
                    "board_name",
                    "discovered",
                    "enqueued",
                    "board_updated",
                    "crawled",
                    "imports",
                    "stubs",
                    "retries",
                    "skipped",
                    "failed",
                    "soft_browser_retried",
                    "pages_scanned",
                    "reason",
                    "error",
                    "list_sort",
                    "queue_kind",
                )
            }


async def run_scan_head_once(
    *,
    forum_id: str = SITE_CRAWLER_FORUM_ID,
    max_pages: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """手动扫新帖：按启用队列顺序逐板首页捕新；每板达上限或扫完后换下一板。"""
    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        cfg = dict(configs.get(forum_id) or {})
    finally:
        conn.close()
    enabled = resolve_enabled_board_fids(cfg)
    if not enabled:
        return {"ok": False, "skipped": True, "reason": "no_enabled_boards", "error": "未选择工作板块"}

    _log_activity(
        f"手动扫新帖 · 启用 {len(enabled)} 板 · 顺序 {' → '.join(enabled)}"
    )
    agg: dict[str, Any] = {
        "ok": True,
        "scan_head": True,
        "deep_scan": False,
        "enabled_board_fids": enabled,
        "boards": [],
        "discovered": 0,
        "enqueued": 0,
        "crawled": 0,
        "imports": 0,
        "stubs": 0,
        "retries": 0,
        "failed": 0,
        "pages_head": [],
        "pages_scanned": [],
    }
    last: dict[str, Any] = {}
    for fid in enabled:
        if THROTTLE.should_stop():
            agg["reason"] = "stopped"
            break
        if max_pages is not None:
            pages = max(1, int(max_pages))
        else:
            pages = resolve_manual_head_pages(cfg, fid)
        _log_activity(f"扫新帖 · 板块 {fid} · 上限 {pages} 页")
        last = await run_crawl_once(
            forum_id=forum_id,
            persist=persist,
            scan_list=True,
            scan_head=True,
            deep_scan=False,
            head_pages_override=pages,
            board_fid_override=fid,
            from_loop=False,
            require_enabled=False,
        )
        if last.get("skipped"):
            agg["ok"] = False
            agg["skipped"] = True
            agg["reason"] = last.get("reason")
            agg["error"] = last.get("error")
            break
        board_summary = {
            "board_fid": last.get("board_fid"),
            "board_name": last.get("board_name"),
            "pages_head": last.get("pages_head") or [],
            "enqueued": last.get("enqueued") or 0,
            "discovered": last.get("discovered") or 0,
            "crawled": last.get("crawled") or 0,
            "imports": last.get("imports") or 0,
            "head_completed": last.get("head_completed"),
            "head_incomplete": bool(last.get("head_incomplete")),
            "reason": last.get("reason"),
        }
        agg["boards"].append(board_summary)
        for key in ("discovered", "enqueued", "crawled", "imports", "stubs", "retries", "failed"):
            agg[key] = int(agg.get(key) or 0) + int(last.get(key) or 0)
        agg["pages_head"] = list(agg.get("pages_head") or []) + list(last.get("pages_head") or [])
        if last.get("ok") is False:
            agg["ok"] = False
            agg["error"] = last.get("error") or last.get("reason")
            if last.get("reason") in {"list_login_required", "cooldown_tripped", "stopped"}:
                agg["reason"] = last.get("reason")
                break
        # 达上限或扫完均已于本板 run 内结束，继续下一启用板
        # 刷新 cfg 以便后续板读到最新进度
        conn = connect()
        try:
            configs = load_forum_configs_map(conn)
            cfg = dict(configs.get(forum_id) or {})
        finally:
            conn.close()

    if last:
        agg["board_fid"] = last.get("board_fid")
        agg["board_name"] = last.get("board_name")
        if last.get("reason") and not agg.get("reason"):
            agg["reason"] = last.get("reason")
    _STATE["last_result"] = {
        k: agg.get(k)
        for k in (
            "ok",
            "enabled_board_fids",
            "boards",
            "discovered",
            "enqueued",
            "crawled",
            "imports",
            "stubs",
            "retries",
            "reason",
            "error",
        )
    }
    _log_activity(
        f"扫新帖汇总 · {len(agg.get('boards') or [])}/{len(enabled)} 板 · "
        f"入队 {agg['enqueued']} · 抓 {agg['crawled']} · 入库 {agg['imports']}"
    )
    return agg


async def _continuous_loop() -> None:
    """拓扑：一轮结束立即再开，无轮间间隔。"""
    _STATE["looping"] = True
    _STATE["running"] = True
    _STATE["loop_kind"] = "deep"
    _log_activity("连续调度已启动 · 无轮间间隔")
    try:
        while _STATE.get("looping") and not THROTTLE.should_stop():
            # reload enabled each round
            conn = connect()
            try:
                configs = load_forum_configs_map(conn)
                cfg = configs.get(SITE_CRAWLER_FORUM_ID) or {}
            finally:
                conn.close()
            if not cfg.get("web_crawler_enabled"):
                _log_activity("开关已关 · 连续调度待命")
                await THROTTLE.sleep_for(5)
                continue
            await run_crawl_once(
                persist=True,
                scan_list=True,
                scan_head=False,
                deep_scan=True,
                from_loop=True,
                require_enabled=True,
            )
            if THROTTLE.should_stop() or not _STATE.get("looping"):
                break
            # 无轮间间隔：立即下一轮（仅极短让出事件循环）
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        _log_activity("连续调度任务已取消")
        raise
    finally:
        _STATE["looping"] = False
        _STATE["running"] = False
        _STATE["loop_kind"] = None
        _STATE["phase"] = "idle"
        _log_activity("连续调度已停止")


def start_continuous_loop() -> dict[str, Any]:
    global _loop_task
    if _STATE.get("looping") and _loop_task and not _loop_task.done():
        return {"ok": True, "already": True, "message": "连续调度已在运行"}
    if _STATE.get("looping") and _STATE.get("loop_kind") == "random_tid":
        return {"ok": False, "already": False, "message": "随机抓帖连续中，请先停止"}
    THROTTLE.clear_stop()
    _STATE["looping"] = True
    _STATE["running"] = True
    _STATE["loop_kind"] = "deep"
    _STATE["phase"] = "scheduler"
    _loop_task = asyncio.get_running_loop().create_task(_continuous_loop())
    return {"ok": True, "message": "连续调度已启动"}


def stop_continuous_loop() -> dict[str, Any]:
    request_stop()
    return {"ok": True, "message": "已请求停止连续调度"}


def _force_idle_state() -> None:
    """卡住时的兜底复位：不碰 Postgres 队列行。"""
    global _round_task
    _STATE["looping"] = False
    _STATE["running"] = False
    _STATE["loop_inner"] = False
    _STATE["loop_kind"] = None
    _STATE["phase"] = "idle"
    _round_task = None


async def stop_crawler(
    *,
    disable: bool = True,
    wait_seconds: float = 12.0,
    force_after: float = 8.0,
) -> dict[str, Any]:
    """手动停止：协作退出 → 超时取消任务 → 会话在 finally 清理；队列行不删不改。"""
    global _loop_task, _round_task

    was_running = bool(_STATE.get("running") or _STATE.get("looping"))
    request_stop()
    _log_activity("手动停止 · 请求线程退出 · 未完成队列将保留")

    if disable:
        try:
            conn = connect()
            try:
                configs = load_forum_configs_map(conn)
                cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
                if cfg.get("web_crawler_enabled"):
                    cfg["web_crawler_enabled"] = False
                    save_forum_config(conn, SITE_CRAWLER_FORUM_ID, cfg)
            finally:
                conn.close()
        except Exception as exc:
            log.warning("stop disable flag: %s", exc)

    deadline = time.monotonic() + max(0.5, float(wait_seconds))
    force_at = time.monotonic() + max(0.5, float(force_after))
    forced = False

    while time.monotonic() < deadline:
        if not _STATE.get("running") and not _STATE.get("looping"):
            break
        if not forced and time.monotonic() >= force_at:
            forced = True
            tasks: list[asyncio.Task] = []
            if _loop_task is not None and not _loop_task.done():
                tasks.append(_loop_task)
            if _round_task is not None and not _round_task.done() and _round_task not in tasks:
                # 同一 task（循环内）只 cancel 一次
                if _loop_task is None or _round_task is not _loop_task:
                    tasks.append(_round_task)
            try:
                from workers.random_tid import cancel_random_loop_task, clear_random_session_state

                for t in cancel_random_loop_task():
                    if t not in tasks:
                        tasks.append(t)
                clear_random_session_state()
            except Exception:
                pass
            for t in tasks:
                t.cancel()
            _log_activity("手动停止 · 超时强制取消任务")
        await asyncio.sleep(0.2)

    still = bool(_STATE.get("running") or _STATE.get("looping") or _STATE.get("loop_inner"))
    if still:
        _force_idle_state()
        _log_activity("手动停止 · 已强制复位状态（队列未改动）")
    else:
        _STATE["phase"] = "idle"
        _log_activity("手动停止完成 · 线程已退出 · 队列任务保留")

    return {
        "ok": True,
        "was_running": was_running,
        "forced": forced,
        "running": bool(_STATE.get("running")),
        "looping": bool(_STATE.get("looping")),
        "queue_preserved": True,
        "message": "已停止 · 未完成队列已保留",
    }
