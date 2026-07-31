"""爬虫活动页 API：状态 / 开关 / 一轮 / 连续调度（对齐拓扑）。"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.deps import require_permission
from db.connection import connect
from db.forum_configs import (
    FULL_CRAWLER_FORUM_IDS,
    SITE_CRAWLER_FORUM_ID,
    build_forums_payload,
    get_active_forum_id,
    load_forum_configs_map,
    resolve_enabled_board_fids,
    save_forum_config,
)
from db.queue import (
    DISCARDED_REQUEUE_KINDS,
    count_discarded,
    count_discarded_kind,
    count_discarded_kinds,
    count_pending,
    count_pending_queue,
    list_discarded,
    list_discarded_reasons,
    list_discarded_tids,
    list_pending_queue,
    list_pending_reasons,
    requeue_discarded_by_tids,
    requeue_discarded_kind,
)
from workers.runner import (
    _log_activity,
    crawl_status,
    recent_activity,
    recover_stuck_after_stop,
    run_crawl_once,
    run_scan_head_once,
    start_continuous_loop,
    stop_continuous_loop,
    stop_crawler,
)
from workers.crawl_executor import await_crawl, spawn_crawl
from workers.random_tid import run_random_tid_batch, start_random_tid_loop

router = APIRouter(prefix="/api/crawler", tags=["crawler"])

# 不合格/占位计数很重；状态轮询 5s 一次，短缓存避免拖死连接池
_STATUS_HEAVY_TTL_SEC = 20.0
_STATUS_HEAVY_LOCK = threading.Lock()
_STATUS_HEAVY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _status_cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _STATUS_HEAVY_LOCK:
        hit = _STATUS_HEAVY_CACHE.get(key)
        if not hit:
            return None
        expires, payload = hit
        if now >= expires:
            _STATUS_HEAVY_CACHE.pop(key, None)
            return None
        return dict(payload)


def _status_cache_set(key: str, payload: dict[str, Any]) -> None:
    with _STATUS_HEAVY_LOCK:
        _STATUS_HEAVY_CACHE[key] = (
            time.monotonic() + _STATUS_HEAVY_TTL_SEC,
            dict(payload),
        )


def _status_cache_clear() -> None:
    with _STATUS_HEAVY_LOCK:
        _STATUS_HEAVY_CACHE.clear()


class EnabledBody(BaseModel):
    enabled: bool = True
    # 空 = 跟随当前启用论坛（勿写死色花堂）
    forum_id: str = ""


class RunBody(BaseModel):
    forum_id: str = ""
    persist: bool = True
    max_threads: int | None = Field(default=None, ge=1, le=500)
    scan_list: bool = True


class ScanHeadBody(BaseModel):
    forum_id: str = ""
    persist: bool = True
    max_pages: int | None = Field(default=None, ge=1, le=200)


class RandomTidBody(BaseModel):
    forum_id: str = ""
    persist: bool = True
    count: int | None = Field(default=None, ge=1, le=500, description="探测 tid 数上限")
    import_target: int | None = Field(
        default=None, ge=0, le=200, description="入库+占位目标；0=跑满本轮探测"
    )
    tid_min: int | None = Field(default=None, ge=1, le=50_000_000)
    tid_max: int | None = Field(default=None, ge=1, le=50_000_000)


class RandomTidLoopBody(BaseModel):
    forum_id: str = ""
    count: int | None = Field(default=200, ge=1, le=500, description="每轮随机探测数")
    tid_min: int | None = Field(default=None, ge=1, le=50_000_000)
    tid_max: int | None = Field(default=None, ge=1, le=50_000_000)


class RecrawlStubsBody(BaseModel):
    forum_id: str = ""


def _resolve_crawler_forum_id(raw: str | None = None) -> str:
    """优先请求体 forum_id，否则调度焦点论坛，最后回退色花堂。"""
    fid = (raw or "").strip()
    if fid in FULL_CRAWLER_FORUM_IDS:
        return fid
    conn = connect()
    try:
        active = (get_active_forum_id(conn) or "").strip()
    finally:
        conn.close()
    if active in FULL_CRAWLER_FORUM_IDS:
        return active
    return SITE_CRAWLER_FORUM_ID


@router.get("/status")
def get_crawler_status(
    since_id: int = 0,
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    from crawler.list_urls import site_root
    from crawler.sites import get_site_adapter
    from parsers.boards import enabled_queue_board_keys, queue_board_keys

    # 紧急/手动停止后 running+stop 可能残留；轮询时幂等复位，避免 UI 一直忙碌
    recover_stuck_after_stop()

    active = SITE_CRAWLER_FORUM_ID
    active_forum_name = SITE_CRAWLER_FORUM_ID
    active_forum: dict | None = None
    cfg_forum_id = SITE_CRAWLER_FORUM_ID
    cfg: dict = {}
    board_fid = ""
    enabled_fids: list[str] = []
    enabled_crawler_ids: list[str] = []
    qstats: dict = {}
    discarded_stats: dict = {}
    discarded_access_denied = 0
    discarded_failed_kind = 0
    active_ready = 0

    conn = connect()
    try:
        payload = build_forums_payload(conn)
        active = str(
            payload.get("focus_forum_id")
            or payload.get("active_forum_id")
            or get_active_forum_id(conn)
            or SITE_CRAWLER_FORUM_ID
        )
        forums = list(payload.get("forums") or [])
        active_forum = next((f for f in forums if str(f.get("id")) == active), None) or next(
            (f for f in forums if str(f.get("id")) == SITE_CRAWLER_FORUM_ID), None
        )
        active_forum_name = str((active_forum or {}).get("name") or active)
        configs = load_forum_configs_map(conn)
        enabled_crawler_ids = list(payload.get("enabled_crawler_forum_ids") or [])
        # 状态面板跟随「调度焦点」；无专爬时回退站点专爬配置
        cfg_forum_id = active if active in configs else SITE_CRAWLER_FORUM_ID
        cfg = dict(configs.get(cfg_forum_id) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        board_fid = str(cfg.get("active_board_fid") or "")
        enabled_fids = resolve_enabled_board_fids(cfg, forum_id=cfg_forum_id)

        # 正常队列 = 启用子板全部待抓合计；短缓存避免 5s 轮询反复 COUNT
        queue_keys = enabled_queue_board_keys(enabled_fids)
        if not queue_keys and board_fid:
            queue_keys = queue_board_keys(board_fid)
        qk = ",".join(sorted(str(k) for k in (queue_keys or [])))
        queue_cache_key = f"status_queue:{active}:{board_fid}:{qk}"
        cached_queue = _status_cache_get(queue_cache_key)
        if cached_queue is not None:
            qstats = dict(cached_queue.get("qstats") or {})
            discarded_stats = dict(cached_queue.get("discarded_stats") or {})
            discarded_access_denied = int(
                cached_queue.get("discarded_access_denied") or 0
            )
            discarded_failed_kind = int(
                cached_queue.get("discarded_failed_kind") or 0
            )
            active_ready = int(cached_queue.get("active_ready") or 0)
        else:
            try:
                qstats = count_pending(conn, board_fid=queue_keys or None)
            except Exception:
                qstats = {}
            try:
                discarded_bundle = count_discarded(
                    conn,
                    status="all",
                    forum_id=active,
                    with_requeue_kinds=True,
                )
                discarded_stats = {
                    "failed": int(discarded_bundle.get("failed") or 0),
                    "skipped": int(discarded_bundle.get("skipped") or 0),
                    "total": int(discarded_bundle.get("total") or 0),
                }
                discarded_access_denied = int(
                    discarded_bundle.get("access_denied_bad_title") or 0
                )
                discarded_failed_kind = int(discarded_bundle.get("failed_all") or 0)
            except Exception:
                discarded_stats = {}
                discarded_access_denied = 0
                discarded_failed_kind = 0
            if board_fid:
                try:
                    active_ready = int(
                        count_pending(
                            conn, board_fid=queue_board_keys(board_fid)
                        ).get("ready")
                        or 0
                    )
                except Exception:
                    active_ready = 0
            _status_cache_set(
                queue_cache_key,
                {
                    "qstats": qstats,
                    "discarded_stats": discarded_stats,
                    "discarded_access_denied": discarded_access_denied,
                    "discarded_failed_kind": discarded_failed_kind,
                    "active_ready": active_ready,
                },
            )
    finally:
        conn.close()

    priority_stubs = 0
    frame_fail_total = 0
    try:
        from db.repository import count_frame_fail_posts, count_priority_account_stubs
        from db.resource_db import connect_resource

        cache_key = f"status_heavy:{active}"
        cached = _status_cache_get(cache_key)
        if cached is not None:
            priority_stubs = int(cached.get("priority_stubs") or 0)
            frame_fail_total = int(cached.get("frame_fail_total") or 0)
        else:
            rconn = connect_resource()
            try:
                priority_stubs = int(
                    count_priority_account_stubs(rconn, forum_id=active) or 0
                )
                # 状态面板只要不合格总数，勿拆 7 桶（原先可达分钟级）
                frame_fail_total = int(
                    (
                        count_frame_fail_posts(
                            rconn, forum_id=active, breakdown=False
                        )
                        or {}
                    ).get("total")
                    or 0
                )
            finally:
                rconn.close()
            _status_cache_set(
                cache_key,
                {
                    "priority_stubs": priority_stubs,
                    "frame_fail_total": frame_fail_total,
                },
            )
    except Exception:
        priority_stubs = 0
        frame_fail_total = 0

    adapter = get_site_adapter(cfg_forum_id)
    policies = adapter.board_policies()
    boards: list[dict] = []
    for efid in enabled_fids:
        if efid not in policies:
            continue
        pol = policies[efid]
        boards.append(
            {
                "key": pol.key,
                "fid": str(pol.fid),
                "typeid": pol.list_typeid or "",
                "name": pol.name,
                "pending": active_ready if efid == board_fid else "—",
                "done": "—",
                "current": efid == board_fid,
            }
        )

    st = crawl_status()
    last = st.get("last_result") or {}
    running_forum_id = str(st.get("forum_id") or "").strip() or (
        cfg_forum_id if st.get("running") or st.get("looping") else ""
    )
    try:
        from workers.random_tid import random_progress

        rnd = random_progress()
    except Exception:
        rnd = {}
    try:
        from workers.recrawl import account_stub_progress

        stub_prog = account_stub_progress()
    except Exception:
        stub_prog = {}
    try:
        from workers.attach_queue_runner import attach_queue_progress

        attach_prog = attach_queue_progress()
    except Exception:
        attach_prog = {}

    # 列表扫进行中：内存游标优先（每页已同步落库，这里再叠一层防读库延迟）
    board_cursors = dict(cfg.get("board_list_cursors") or {})
    if str(st.get("phase") or "") == "list_scan":
        for ck, pg in dict(st.get("board_list_cursors") or {}).items():
            try:
                board_cursors[str(ck)] = max(0, int(pg or 0))
            except (TypeError, ValueError):
                continue

    try:
        from workers.import_rate import import_rate_snapshot

        import_rate = import_rate_snapshot()
    except Exception:
        import_rate = {"per_minute": 0, "window_sec": 60}

    preferred_entry = str(cfg.get("preferred_entry_url") or "").strip()
    crawl_urls = str(cfg.get("web_crawl_urls") or "").strip()
    first_crawl = next((u.strip() for u in crawl_urls.split(",") if u.strip()), "")
    thread_root = site_root(preferred_entry or first_crawl or str((active_forum or {}).get("base_url") or ""))

    from db.activity import latest_activity_id, list_recent_activity

    since = max(0, int(since_id or 0))
    try:
        activities = list_recent_activity(120, since_id=since)
    except Exception:
        activities = recent_activity(120)
    try:
        latest_id = latest_activity_id()
    except Exception:
        latest_id = max((int(a.get("id") or 0) for a in activities), default=0)

    metrics = {
        "discovered": last.get("discovered") or 0,
        "enqueued": last.get("enqueued") or 0,
        "crawled": last.get("crawled") or 0,
        "imports": last.get("imports") or 0,
        "stubs": last.get("stubs") or 0,
        "retries": last.get("retries") or 0,
        "soft_browser_retried": last.get("soft_browser_retried") or 0,
        "queue_ready": (qstats or {}).get("ready") or 0,
        "queue_ready_active": active_ready,
        "queue_soft_ad": (qstats or {}).get("soft_ad") or 0,
        "queue_abnormal": (qstats or {}).get("abnormal") or 0,
        "queue_deferred": (qstats or {}).get("deferred") or 0,
        "discarded_failed": (discarded_stats or {}).get("failed") or 0,
        "discarded_skipped": (discarded_stats or {}).get("skipped") or 0,
        "discarded_total": (discarded_stats or {}).get("total") or 0,
        "random_probed": rnd.get("probed") or 0,
        "random_budget": rnd.get("probe_budget") or 0,
        "random_imported": rnd.get("imported") or 0,
        "random_session": rnd.get("session_probed") or 0,
        "stub_done": stub_prog.get("done") or 0,
        "stub_budget": stub_prog.get("remaining") or stub_prog.get("budget") or 0,
        "stub_remaining": stub_prog.get("remaining") or stub_prog.get("budget") or 0,
        "stub_upgraded": stub_prog.get("upgraded") or 0,
        "priority_stubs": priority_stubs,
        "frame_fail_total": frame_fail_total,
        "discarded_access_denied_title": discarded_access_denied,
        "discarded_failed_kind": discarded_failed_kind,
        "account_pass_total": (
            int(priority_stubs) + int(discarded_access_denied) + int(discarded_failed_kind)
        ),
        "board_updated": last.get("board_updated") or 0,
        "imports_per_minute": import_rate.get("per_minute") or 0,
    }
    try:
        from workers.account_stub_daily import daily_status, resolve_daily_limit

        _daily = daily_status(
            str(active or cfg_forum_id or ""),
            resolve_daily_limit(cfg),
        )
        metrics["account_stub_daily_limit"] = int(_daily.get("limit") or 0)
        metrics["account_stub_daily_used"] = int(_daily.get("used") or 0)
        metrics["account_stub_daily_remaining"] = _daily.get("remaining")
    except Exception:
        metrics["account_stub_daily_limit"] = int(
            cfg.get("web_crawler_account_stub_daily_limit") or 50
        )
        metrics["account_stub_daily_used"] = 0
        metrics["account_stub_daily_remaining"] = metrics["account_stub_daily_limit"]
    throttle = st.get("throttle") or {}
    runtime = {
        "enabled": bool(cfg.get("web_crawler_enabled")),
        "running": bool(st.get("running") or st.get("looping")),
        "looping": bool(st.get("looping")),
        "stopping": bool(st.get("stopping")),
        "phase": st.get("phase") or "idle",
        "active_forum_id": active,
        "forum_id": cfg_forum_id,
        "crawler_registered": bool((active_forum or {}).get("crawler_registered")),
        "interval_minutes": 0,
        "list_pages_per_board": cfg.get("web_crawler_list_pages_per_board"),
        "pending_queue": (qstats or {}).get("ready") or 0,
        "pending_discovered": (qstats or {}).get("ready") or 0,
        "pending_abnormal_discovered": (qstats or {}).get("abnormal") or 0,
        "pending_soft_ad": (qstats or {}).get("soft_ad") or 0,
        "pending_carryover": (qstats or {}).get("deferred") or 0,
        "run_crawled_threads": last.get("crawled") or 0,
        "run_links_imported": last.get("imports") or 0,
        "risk_control_tripped": bool(throttle.get("tripped") or throttle.get("risk_tripped")),
        "risk_control_message": str(throttle.get("message") or throttle.get("risk_message") or ""),
        "fetch_delay_current": throttle.get("delay_current") or throttle.get("current_delay"),
        "fetch_delay_base": throttle.get("delay_base") or cfg.get("web_crawler_request_delay"),
        "fetch_delay_max": throttle.get("delay_max") or cfg.get("web_crawler_autothrottle_max_delay"),
        "fetch_success_rate": throttle.get("success_rate"),
        "fetch_sample_size": throttle.get("sample_size"),
        "fetch_failure_threshold": cfg.get("web_crawler_fetch_failure_threshold"),
        "preferred_entry_url": preferred_entry,
        "thread_root": thread_root,
    }

    return {
        "forum_id": cfg_forum_id,
        "active_forum_id": active,
        "focus_forum_id": active,
        "active_forum_name": active_forum_name,
        "running_forum_id": running_forum_id or None,
        "enabled_crawler_forum_ids": enabled_crawler_ids,
        "scheduling_model": "single_process_focus",
        "enabled": bool(cfg.get("web_crawler_enabled")),
        "active_board_fid": board_fid,
        "enabled_board_fids": enabled_fids,
        "request_delay": cfg.get("web_crawler_request_delay"),
        "list_pages_per_board": cfg.get("web_crawler_list_pages_per_board"),
        "list_head_pages": cfg.get("web_crawler_list_head_pages"),
        "manual_head_pages": cfg.get("web_crawler_manual_head_pages"),
        "list_known_stop_pages": cfg.get("web_crawler_list_known_stop_pages"),
        "list_sort": "dateline",
        "list_sort_label": "按发帖时间",
        "list_strategy": "manual_head+auto_deep",
        "interval_minutes": 0,
        "interval_label": "连续无间隔",
        "running": bool(st.get("running")),
        "looping": bool(st.get("looping")),
        "loop_kind": st.get("loop_kind"),
        "stopping": bool(st.get("stopping")),
        "phase": st.get("phase") or "idle",
        "last_started_at": st.get("last_started_at"),
        "last_finished_at": st.get("last_finished_at"),
        "last_result": last,
        "random_progress": rnd,
        "account_stub_progress": stub_prog,
        "attach_queue_progress": attach_prog,
        "board_list_cursors": board_cursors,
        "web_crawl_urls": crawl_urls,
        "preferred_entry_url": preferred_entry,
        "thread_root": thread_root,
        "activity": activities,
        "activities": activities,
        "latest_activity_id": latest_id,
        "runtime": runtime,
        "boards": boards,
        "queue": qstats or st.get("queue") or {},
        "discarded": discarded_stats or {},
        "throttle": throttle,
        "metrics": metrics,
        "import_rate": import_rate,
    }


@router.post("/activity/clear")
def clear_crawler_activity(
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """清空爬虫活动日志面板（仅 crawl_activity_log，不动队列/游标）。"""
    from db.activity import clear_activity_log

    deleted = clear_activity_log()
    # 清完写一条提示，方便确认面板已刷新
    _log_activity(f"活动日志已清空 · 删除 {deleted} 条")
    from db.activity import latest_activity_id, list_recent_activity

    activities = list_recent_activity(120)
    return {
        "message": "success",
        "deleted": deleted,
        "activity": activities,
        "activities": activities,
        "latest_activity_id": latest_activity_id(),
    }


@router.put("/enabled")
async def put_crawler_enabled(
    body: EnabledBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")

    # 关闭开关 = 与「手动停止」同路径：协作退出 → 超时取消任务 → 队列保留
    if not body.enabled:
        stop_result = await stop_crawler(disable=True, wait_seconds=12.0, force_after=8.0)
        _log_activity("论坛爬虫开关已关闭 · 线程退出 · 队列已保留")
        return {
            "message": "success",
            "forum_id": fid,
            "enabled": False,
            "stopped": True,
            "queue_preserved": True,
            "forced": bool(stop_result.get("forced")),
            "status": crawl_status(),
        }

    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        cfg = dict(configs.get(fid) or {})
        cfg["web_crawler_enabled"] = True
        saved = save_forum_config(conn, fid, cfg)
        _log_activity(f"论坛爬虫已开启 · {fid}")
        return {
            "message": "success",
            "forum_id": fid,
            "enabled": bool(saved.get("web_crawler_enabled")),
            "config": saved,
        }
    finally:
        conn.close()


def _require_manual_idle(*, action: str) -> None:
    """手动操作前：连续调度拒绝；停止后卡住的 running+stop 则复位。"""
    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail=f"正在自动爬取中，请先点停止后再{action}")
    recover_stuck_after_stop(activity=action)
    st = crawl_status()
    if st.get("running"):
        raise HTTPException(status_code=409, detail="爬虫正在处理其他任务，请稍候")


@router.post("/run")
async def post_crawler_run(
    body: RunBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动立即爬取：只跑一轮；连续调度启用时不可触发。"""
    body = body or RunBody()
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    _require_manual_idle(action="立即爬取")
    result = await await_crawl(
        run_crawl_once(
            forum_id=fid,
            persist=body.persist,
            max_threads=body.max_threads,
            scan_list=body.scan_list,
            scan_head=False,
            deep_scan=True,
            from_loop=False,
            require_enabled=False,
        ),
        name="crawler-run",
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "正在自动爬取中，请先点停止"))
    return {"message": "ok" if result.get("ok") and not result.get("skipped") else "failed", "result": result}


@router.post("/scan-head")
async def post_crawler_scan_head(
    body: ScanHeadBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动扫新帖：首页捕新入队，本轮不做深扫；连续调度启用时不可触发。"""
    body = body or ScanHeadBody()
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    _require_manual_idle(action="扫新帖")
    result = await await_crawl(
        run_scan_head_once(
            forum_id=fid,
            max_pages=body.max_pages,
            persist=body.persist,
        ),
        name="crawler-scan-head",
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "正在自动爬取中，请先点停止"))
    if result.get("reason") == "already_running":
        raise HTTPException(status_code=409, detail="爬虫正在处理其他任务，请稍候")
    return {"message": "ok" if result.get("ok") and not result.get("skipped") else "failed", "result": result}


@router.post("/random-tid")
async def post_crawler_random_tid(
    body: RandomTidBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动随机抓帖：tid 直链探测早期帖，magnet+ed2k 混合判定入库。"""
    body = body or RandomTidBody()
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    _require_manual_idle(action="随机抓帖")
    result = await await_crawl(
        run_random_tid_batch(
            forum_id=fid,
            probe=body.count,
            import_target=body.import_target,
            tid_min=body.tid_min,
            tid_max=body.tid_max,
            persist=body.persist,
        ),
        name="crawler-random-tid",
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "正在自动爬取中，请先点停止"))
    if result.get("reason") == "busy":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "爬虫正在处理其他任务，请稍候"))
    ok = bool(result.get("ok") and not result.get("skipped"))
    return {
        "message": "ok" if ok else "failed",
        "result": result,
        "probed": result.get("probed") or 0,
        "imported": result.get("imported") or 0,
        "stubbed": result.get("stubbed") or 0,
        "missing": result.get("missing") or 0,
        "skipped_dup": result.get("skipped_dup") or 0,
    }


@router.post("/random-tid/loop/start")
async def post_crawler_random_tid_loop_start(
    body: RandomTidLoopBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """启动随机抓帖连续循环：每轮 count 个随机 tid，跳过已入库，无间隔再开下一轮。"""
    body = body or RandomTidLoopBody()
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    result = start_random_tid_loop(
        forum_id=fid,
        probe=body.count if body.count is not None else 200,
        tid_min=body.tid_min,
        tid_max=body.tid_max,
    )
    if result.get("already"):
        return {"message": "already", "looping": True, "loop_kind": "random_tid", **result}
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=str(result.get("error") or "无法启动"))
    _log_activity(str(result.get("message") or "随机抓帖连续调度已启动"))
    return {
        "message": "started",
        "looping": True,
        "loop_kind": "random_tid",
        "probe": result.get("probe") or body.count or 200,
    }


@router.post("/loop/start")
async def post_loop_start(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """启动拓扑连续调度：一轮结束立即再开。"""
    result = start_continuous_loop()
    if not result.get("already"):
        _log_activity("已请求启动连续调度")
    return {
        "message": "already" if result.get("already") else "started",
        "looping": True,
    }


@router.post("/loop/stop")
async def post_loop_stop(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    stop_continuous_loop()
    _log_activity("已请求停止连续调度")
    return {"message": "stopping", "looping": False}


@router.post("/stop")
async def post_crawler_stop(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """手动停止：立刻取消任务并关开关；队列任务不删除。"""
    result = await stop_crawler(disable=True, wait_seconds=2.0)
    return {
        "message": result.get("message") or "stopped",
        **result,
        "status": crawl_status(),
    }


async def _post_queue_retry(kind: str) -> dict:
    _require_manual_idle(action="异常重试")
    # 必须跟调度焦点一致；默认 SITE 色花堂会漏掉 2048 异常池
    fid = _resolve_crawler_forum_id()
    result = await await_crawl(
        run_crawl_once(
            forum_id=fid,
            persist=True,
            scan_list=False,
            from_loop=False,
            require_enabled=False,
            queue_kind=kind,
        ),
        name=f"crawler-queue-{kind}",
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "正在自动爬取中，请先点停止"))
    if result.get("skipped") or result.get("ok") is False:
        detail = str(
            result.get("error")
            or result.get("reason")
            or "异常重试未执行"
        )
        raise HTTPException(status_code=409, detail=detail)
    return {
        "message": "ok",
        "kind": kind,
        "crawled": result.get("crawled") or 0,
        "imports": result.get("imports") or 0,
        "stubs": result.get("stubs") or 0,
        "retries": result.get("retries") or 0,
        "failed": result.get("failed") or 0,
        "result": result,
    }


@router.post("/queue/retry-abnormal")
async def post_retry_abnormal(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """重爬异常队列（含原软文壳）；成功才出队。"""
    return await _post_queue_retry("abnormal")


@router.get("/queue/browse")
def get_queue_browse(
    kind: str = "ready",
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    status: str = "all",
    reason: str = "",
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    """队列/占位明细分页：ready | abnormal | discarded | stubs | frame_fail。"""
    from parsers.boards import enabled_queue_board_keys, queue_board_keys

    key = (kind or "ready").strip().lower()
    if key not in {"ready", "abnormal", "discarded", "stubs", "frame_fail"}:
        raise HTTPException(
            status_code=400,
            detail="kind 仅支持 ready / abnormal / discarded / stubs / frame_fail",
        )
    lim = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    query = (q or "").strip()
    reason_key = (reason or "").strip()

    if key == "frame_fail":
        from db.repository import (
            count_frame_fail_posts,
            list_frame_fail_posts,
            list_frame_fail_reasons,
        )
        from db.resource_db import connect_resource

        st = (status or "all").strip().lower()
        if st not in {
            "all",
            "name",
            "link",
            "preview",
            "capacity",
            "review",
            "structure",
            "reviewed",
            "资源名",
            "链接",
            "预览",
            "容量",
            "待核",
            "结构",
            "已审",
            "manual",
        }:
            raise HTTPException(
                status_code=400,
                detail="status 仅支持 all / name / link / preview / capacity / review / reviewed",
            )
        focus = _resolve_crawler_forum_id()
        rconn = connect_resource()
        try:
            # 无搜索时一次 FILTER 带齐各桶 + 已审；有搜索仍一次 breakdown（含 reviewed）
            counts = count_frame_fail_posts(
                rconn, status="all", q=query, forum_id=focus
            )
            reviewed_n = int(counts.get("reviewed") or 0)

            def _tab_total(c: dict, tab: str) -> int:
                t = (tab or "all").strip().lower()
                if t in {"reviewed", "已审", "manual"}:
                    return int(c.get("reviewed") or 0)
                if t in {"name", "资源名"}:
                    return int(c.get("name") or 0)
                if t in {"link", "链接"}:
                    return int(c.get("link") or 0)
                if t in {"preview", "预览"}:
                    return int(c.get("preview") or 0)
                if t in {"capacity", "容量"}:
                    return int(c.get("capacity") or 0)
                if t in {"review", "待核"}:
                    return int(c.get("review") or 0)
                if t in {"structure", "结构"}:
                    return int(c.get("structure") or 0)
                return int(c.get("total") or 0)

            if reason_key:
                total = int(
                    count_frame_fail_posts(
                        rconn,
                        status=st,
                        q=query,
                        reason=reason_key,
                        forum_id=focus,
                    ).get("total")
                    or 0
                )
            else:
                total = _tab_total(counts, st)
            items = list_frame_fail_posts(
                rconn,
                status=st,
                q=query,
                reason=reason_key or None,
                limit=lim,
                offset=off,
                forum_id=focus,
            )
            reasons = list_frame_fail_reasons(
                rconn, status=st, q=query, forum_id=focus
            )
        finally:
            rconn.close()
        return {
            "kind": key,
            "status": st,
            "q": query,
            "reason": reason_key,
            "forum_id": focus,
            "limit": lim,
            "offset": off,
            "total": int(total),
            "counts": {**counts, "reviewed": reviewed_n},
            "reasons": reasons,
            "items": items,
        }

    if key == "discarded":
        st = (status or "all").strip().lower()
        if st not in {"all", "failed", "skipped"}:
            raise HTTPException(status_code=400, detail="status 仅支持 all / failed / skipped")
        focus = _resolve_crawler_forum_id()
        conn = connect()
        try:
            counts = count_discarded(conn, status=st, q=query, forum_id=focus)
            total = (
                count_discarded(
                    conn, status=st, q=query, reason=reason_key, forum_id=focus
                )["total"]
                if reason_key
                else int(counts.get("total") or 0)
            )
            items = list_discarded(
                conn,
                status=st,
                q=query,
                reason=reason_key or None,
                limit=lim,
                offset=off,
                forum_id=focus,
            )
            reasons = list_discarded_reasons(conn, status=st, q=query, forum_id=focus)
            kind_counts = count_discarded_kinds(conn, forum_id=focus)
        finally:
            conn.close()
        return {
            "kind": key,
            "status": st,
            "q": query,
            "reason": reason_key,
            "forum_id": focus,
            "limit": lim,
            "offset": off,
            "total": int(total),
            "counts": counts,
            "kind_counts": kind_counts,
            "reasons": reasons,
            "items": items,
        }

    if key == "stubs":
        from db.repository import (
            count_priority_account_stubs_q,
            list_priority_account_stub_reasons,
            list_priority_account_stubs,
        )
        from db.resource_db import connect_resource

        focus = _resolve_crawler_forum_id()
        rconn = connect_resource()
        try:
            total = count_priority_account_stubs_q(
                rconn, q=query, reason=reason_key or None, forum_id=focus
            )
            items = list_priority_account_stubs(
                rconn,
                limit=lim,
                offset=off,
                q=query,
                reason=reason_key or None,
                forum_id=focus,
            )
            reasons = list_priority_account_stub_reasons(
                rconn, q=query, forum_id=focus
            )
        finally:
            rconn.close()
        return {
            "kind": key,
            "q": query,
            "reason": reason_key,
            "forum_id": focus,
            "limit": lim,
            "offset": off,
            "total": int(total),
            "reasons": reasons,
            "items": items,
        }

    # ready / abnormal
    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        active = get_active_forum_id(conn)
        cfg = dict(configs.get(active) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        enabled_fids = resolve_enabled_board_fids(cfg, forum_id=active)
        queue_keys = enabled_queue_board_keys(enabled_fids)
        if not queue_keys:
            board_fid = str(cfg.get("active_board_fid") or "")
            if board_fid:
                queue_keys = queue_board_keys(board_fid)
        total = count_pending_queue(
            conn,
            kind=key,
            board_fid=queue_keys or None,
            q=query,
            reason=reason_key or None,
        )
        items = list_pending_queue(
            conn,
            kind=key,
            board_fid=queue_keys or None,
            q=query,
            reason=reason_key or None,
            limit=lim,
            offset=off,
        )
        reasons = list_pending_reasons(
            conn, kind=key, board_fid=queue_keys or None, q=query
        )
    finally:
        conn.close()
    return {
        "kind": key,
        "q": query,
        "reason": reason_key,
        "limit": lim,
        "offset": off,
        "total": int(total),
        "reasons": reasons,
        "items": items,
    }


@router.get("/queue/discarded")
def get_queue_discarded(
    status: str = "all",
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    """入队后未正常入库/占位的明细：失败（含重试耗尽丢弃）与跳过。"""
    st = (status or "all").strip().lower()
    if st not in {"all", "failed", "skipped"}:
        raise HTTPException(status_code=400, detail="status 仅支持 all / failed / skipped")
    lim = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    focus = _resolve_crawler_forum_id()
    conn = connect()
    try:
        counts = count_discarded(conn, status=st, q=q, forum_id=focus)
        items = list_discarded(
            conn, status=st, q=q, limit=lim, offset=off, forum_id=focus
        )
        kind_counts = count_discarded_kinds(conn, forum_id=focus)
    finally:
        conn.close()
    return {
        "status": st,
        "q": (q or "").strip(),
        "forum_id": focus,
        "limit": lim,
        "offset": off,
        "total": int(counts.get("total") or 0),
        "counts": {
            "failed": int(counts.get("failed") or 0),
            "skipped": int(counts.get("skipped") or 0),
            "total": int(counts.get("total") or 0),
        },
        "kind_counts": kind_counts,
        "items": items,
    }


@router.get("/queue/discarded/tids")
def get_discarded_tids(
    status: str = "all",
    q: str = "",
    reason: str = "",
    limit: int = 2000,
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    """当前筛选条件下全部 tid（跨页全选）。"""
    st = (status or "all").strip().lower()
    if st not in {"all", "failed", "skipped"}:
        raise HTTPException(status_code=400, detail="status 仅支持 all / failed / skipped")
    lim = max(1, min(5000, int(limit or 2000)))
    query = (q or "").strip()
    reason_key = (reason or "").strip()
    focus = _resolve_crawler_forum_id()
    conn = connect()
    try:
        total = int(
            count_discarded(
                conn, status=st, q=query, reason=reason_key or None, forum_id=focus
            ).get("total")
            or 0
        )
        tids = list_discarded_tids(
            conn,
            status=st,
            q=query,
            reason=reason_key or None,
            limit=lim,
            forum_id=focus,
        )
    finally:
        conn.close()
    return {
        "status": st,
        "q": query,
        "reason": reason_key,
        "forum_id": focus,
        "total": total,
        "limit": lim,
        "count": len(tids),
        "truncated": total > len(tids),
        "tids": tids,
    }


@router.get("/queue/frame-fail/tids")
def get_frame_fail_tids(
    status: str = "all",
    q: str = "",
    reason: str = "",
    limit: int = 2000,
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    """不合格明细当前筛选下全部 tid（跨页全选重爬）。"""
    from db.repository import count_frame_fail_posts, list_frame_fail_tids
    from db.resource_db import connect_resource

    st = (status or "all").strip().lower()
    if st not in {
        "all",
        "name",
        "link",
        "preview",
        "capacity",
        "review",
        "structure",
        "reviewed",
        "资源名",
        "链接",
        "预览",
        "容量",
        "待核",
        "结构",
        "已审",
        "manual",
    }:
        raise HTTPException(
            status_code=400, detail="status 仅支持 all / name / link / preview / capacity / review / reviewed"
        )
    lim = max(1, min(5000, int(limit or 2000)))
    query = (q or "").strip()
    reason_key = (reason or "").strip()
    focus = _resolve_crawler_forum_id()
    rconn = connect_resource()
    try:
        total = int(
            count_frame_fail_posts(
                rconn, status=st, q=query, reason=reason_key or None, forum_id=focus
            ).get("total")
            or 0
        )
        items = list_frame_fail_tids(
            rconn,
            status=st,
            q=query,
            reason=reason_key or None,
            limit=lim,
            forum_id=focus,
        )
    finally:
        rconn.close()
    tids = [int(x["tid"]) for x in items if int(x.get("tid") or 0) > 0]
    hashes = [str(x["hash"]) for x in items if str(x.get("hash") or "").strip()]
    return {
        "status": st,
        "q": query,
        "reason": reason_key,
        "forum_id": focus,
        "total": total,
        "limit": lim,
        "count": len(tids),
        "truncated": total > len(tids),
        "tids": tids,
        "hashes": hashes,
        "items": items,
    }


class FrameFailRecrawlTidsBody(BaseModel):
    tids: list[int] = Field(default_factory=list)
    start_crawl: bool = True


class FrameFailMarkReviewedBody(BaseModel):
    tids: list[int] = Field(default_factory=list)
    undo: bool = False


@router.post("/queue/frame-fail/mark-reviewed")
def post_frame_fail_mark_reviewed(
    body: FrameFailMarkReviewedBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """勾选不合格帖：标为人工已审（移出待审列表）；undo 则撤销。"""
    from db.repository import mark_frame_fail_manual_reviewed
    from db.resource_db import connect_resource

    raw_tids = body.tids or []
    if len(raw_tids) > 2000:
        raise HTTPException(status_code=400, detail="一次最多选择 2000 条")
    want: list[int] = []
    seen: set[int] = set()
    for raw in raw_tids:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        want.append(tid)
    if not want:
        raise HTTPException(status_code=400, detail="请至少选择一条有效 tid")

    focus = _resolve_crawler_forum_id()
    rconn = connect_resource()
    try:
        result = mark_frame_fail_manual_reviewed(
            rconn, tids=want, forum_id=focus, undo=bool(body.undo)
        )
    finally:
        rconn.close()
    _status_cache_clear()
    updated = int(result.get("updated") or 0)
    matched = int(result.get("matched") or 0)
    if body.undo:
        note = f"已撤销人工已审 {matched} 帖（更新 {updated} 行）"
    else:
        note = f"已标人工已审 {matched} 帖（更新 {updated} 行）"
    return {
        "ok": True,
        "message": note,
        "note": note,
        "forum_id": focus,
        **result,
    }


@router.post("/queue/frame-fail/recrawl-tids")
async def post_frame_fail_recrawl_tids(
    body: FrameFailRecrawlTidsBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """勾选的不合格帖：按代表 hash 走已入库重爬（空闲后台抓；连续调度则入队）。"""
    from db.resource_db import connect_resource
    from db.repository import resolve_frame_fail_hashes_by_tids
    from workers.recrawl import recrawl_imported_resources
    from workers.runner import recover_stuck_after_stop

    raw_tids = body.tids or []
    if len(raw_tids) > 2000:
        raise HTTPException(status_code=400, detail="一次最多选择 2000 条")
    want: list[int] = []
    seen: set[int] = set()
    for raw in raw_tids:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        want.append(tid)
    if not want:
        raise HTTPException(status_code=400, detail="请至少选择一条有效 tid")

    focus = _resolve_crawler_forum_id()
    rconn = connect_resource()
    try:
        # 按 tid 直查代表 hash（单选/多选同一路径；勿扫明细分页，旧硬顶会漏掉较旧帖）
        resolved = resolve_frame_fail_hashes_by_tids(
            rconn, want, forum_id=focus
        )
        # 焦点论坛过滤落空时再放宽一次，避免「列表能看见、重爬却报不在不合格」
        if not resolved and focus:
            resolved = resolve_frame_fail_hashes_by_tids(
                rconn, want, forum_id=None
            )
    finally:
        rconn.close()

    hashes: list[str] = []
    seen_h: set[str] = set()
    matched = 0
    for row in resolved:
        h = str(row.get("hash") or "").strip()
        if len(h) < 8 or h in seen_h:
            continue
        seen_h.add(h)
        hashes.append(h)
        matched += 1
    if not hashes:
        sample = "、".join(str(t) for t in want[:5])
        more = f" 等 {len(want)} 条" if len(want) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"所选 tid（{sample}{more}）当前库中无不合格/待核 outcome"
                "（可能已重爬合格，或未写入 resource_sources）"
            ),
        )

    if body.start_crawl is False:
        result = await await_crawl(
            recrawl_imported_resources(hashes),
            name="frame-fail-recrawl-queue",
        )
        queued = int(result.get("queued") or 0)
        return {
            "message": "ok",
            "mode": str(result.get("mode") or "queued"),
            "selected": len(want),
            "matched": matched,
            "queued": queued,
            "imported": int(result.get("imported") or 0),
            "note": str(result.get("note") or f"已处理 {matched} 条不合格重爬请求"),
        }

    st = crawl_status()
    if st.get("looping"):
        result = await await_crawl(
            recrawl_imported_resources(hashes),
            name="frame-fail-recrawl-queue",
        )
        queued = int(result.get("queued") or 0)
        _log_activity(f"不合格批量重爬 · 入队 {queued} 条（连续调度中）")
        return {
            "message": "ok",
            "mode": "queued",
            "selected": len(want),
            "matched": matched,
            "queued": queued,
            "imported": 0,
            "note": (
                f"连续调度中：已入队 {queued} 条不合格帖，由调度依次重爬"
                if queued
                else str(result.get("note") or "未能入队")
            ),
        }

    recover_stuck_after_stop(activity="不合格批量重爬")
    st = crawl_status()
    if st.get("running"):
        raise HTTPException(
            status_code=409,
            detail="爬虫正在处理其他任务，请稍等几秒再重爬",
        )

    _log_activity(f"不合格批量重爬 · 后台启动 {len(hashes)} 条")

    async def _job() -> None:
        try:
            result = await recrawl_imported_resources(hashes)
            imported = int(result.get("imported") or 0)
            queued = int(result.get("queued") or 0)
            failed = int(result.get("failed") or 0)
            _log_activity(
                f"不合格批量重爬结束 · 入库 {imported} · 入队 {queued} · 失败 {failed}"
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("background frame_fail recrawl")
            _log_activity(f"不合格批量重爬异常结束 · {exc}")

    spawn_crawl(_job(), name="frame-fail-recrawl")
    return {
        "message": "started",
        "mode": "background",
        "selected": len(want),
        "matched": matched,
        "queued": 0,
        "imported": 0,
        "note": f"已在后台重爬选中的 {matched} 条不合格帖，进度见活动日志",
    }


class DiscardedRequeueBody(BaseModel):
    kind: str = Field(default="access_denied_bad_title")
    start_crawl: bool = True


class DiscardedRequeueTidsBody(BaseModel):
    tids: list[int] = Field(default_factory=list)
    start_crawl: bool = True


async def _maybe_crawl_after_requeue(
    *,
    want_crawl: bool,
    requeued: int,
) -> tuple[dict | None, str]:
    """重入队后可选跑一轮；返回 (crawl_result, crawl_note)。"""
    if not want_crawl or requeued <= 0:
        return None, ""
    recover_stuck_after_stop(activity="入队后抓取")
    st = crawl_status()
    if st.get("looping") or st.get("running"):
        return None, "；爬虫忙，已入队待连续调度/空闲后抓取"
    crawl_result = await await_crawl(
        run_crawl_once(
            forum_id=_resolve_crawler_forum_id(),
            persist=True,
            scan_list=False,
            from_loop=False,
            require_enabled=False,
        ),
        name="crawler-after-requeue",
    )
    if crawl_result.get("reason") == "loop_running":
        return None, "；爬虫忙，已入队待连续调度/空闲后抓取"
    return crawl_result, ""


def _crawl_payload(crawl_result: dict | None) -> dict | None:
    if crawl_result is None:
        return None
    return {
        "crawled": crawl_result.get("crawled") or 0,
        "imports": crawl_result.get("imports") or 0,
        "stubs": crawl_result.get("stubs") or 0,
        "skipped": crawl_result.get("skipped") or 0,
        "retries": crawl_result.get("retries") or 0,
        "failed": crawl_result.get("failed") or 0,
    }


@router.post("/queue/discarded/requeue")
async def post_discarded_requeue(
    body: DiscardedRequeueBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """将某一类未处理（跳过/失败）帖重新入队；可选立刻跑一轮抓取。"""
    kind = (body.kind or "").strip()
    if kind not in DISCARDED_REQUEUE_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind 仅支持: {', '.join(sorted(DISCARDED_REQUEUE_KINDS))}",
        )
    label = str(DISCARDED_REQUEUE_KINDS[kind].get("label") or kind)

    want_crawl = bool(body.start_crawl)

    conn = connect()
    try:
        matched = count_discarded_kind(conn, kind)
        if matched <= 0:
            return {
                "message": "ok",
                "kind": kind,
                "label": label,
                "matched": 0,
                "requeued": 0,
                "crawl": None,
                "note": f"没有「{label}」可重跑",
            }
        requeued = requeue_discarded_kind(conn, kind)
    finally:
        conn.close()

    _log_activity(f"未处理重入队 · {label} · {requeued} 条")

    crawl_result, crawl_note = await _maybe_crawl_after_requeue(
        want_crawl=want_crawl, requeued=requeued
    )

    pending_left = 0
    conn = connect()
    try:
        pending_left = int(count_pending(conn).get("ready") or 0)
        kind_left = count_discarded_kind(conn, kind)
    finally:
        conn.close()

    return {
        "message": "ok",
        "kind": kind,
        "label": label,
        "matched": matched,
        "requeued": requeued,
        "kind_remaining": kind_left,
        "pending_ready": pending_left,
        "crawl": _crawl_payload(crawl_result),
        "note": (
            f"已重新入队 {requeued} 条「{label}」"
            + (
                f"；本轮抓取 {int((crawl_result or {}).get('crawled') or 0)}，"
                f"占位 {int((crawl_result or {}).get('stubs') or 0)}"
                if crawl_result is not None
                else ""
            )
            + crawl_note
            + (f"；待抓队列仍有 {pending_left}" if pending_left else "")
        ),
    }


@router.post("/queue/discarded/requeue-tids")
async def post_discarded_requeue_tids(
    body: DiscardedRequeueTidsBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """勾选的未处理帖：空闲时直接重爬并写活动日志；忙碌/连续调度时仅入队。"""
    from workers.recrawl import recrawl_discarded_tids

    raw_tids = body.tids or []
    if len(raw_tids) > 2000:
        raise HTTPException(status_code=400, detail="一次最多选择 2000 条")
    tids: list[int] = []
    seen: set[int] = set()
    for raw in raw_tids:
        try:
            tid = int(raw)
        except (TypeError, ValueError):
            continue
        if tid <= 0 or tid in seen:
            continue
        seen.add(tid)
        tids.append(tid)
    if not tids:
        raise HTTPException(status_code=400, detail="请至少选择一条有效 tid")

    # start_crawl=False：只入队不抓（仍写日志）
    if body.start_crawl is False:
        conn = connect()
        try:
            requeued = requeue_discarded_by_tids(conn, tids)
        finally:
            conn.close()
        _log_activity(f"未处理批量重入队 · 选中 {len(tids)} · 实际 {requeued} 条")
        pending_left = 0
        conn = connect()
        try:
            pending_left = int(count_pending(conn).get("ready") or 0)
        finally:
            conn.close()
        return {
            "message": "ok",
            "mode": "queued",
            "selected": len(tids),
            "requeued": requeued,
            "crawled": 0,
            "imports": 0,
            "stubs": 0,
            "skipped": 0,
            "failed": 0,
            "pending_ready": pending_left,
            "crawl": None,
            "note": (
                f"已重新入队 {requeued} 条"
                if requeued
                else "所选 tid 均不在失败/跳过队列（可能已处理）"
            )
            + (f"；待抓队列仍有 {pending_left}" if pending_left else ""),
        }

    # 爬虫线程执行：避免浏览器/附件挂死时堵死 uvicorn 主循环
    async def _discarded_job() -> None:
        try:
            await recrawl_discarded_tids(tids)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).exception("background discarded recrawl")
            _log_activity(f"未处理批量重爬异常结束 · {exc}")

    spawn_crawl(_discarded_job(), name="discarded-recrawl")
    pending_left = 0
    conn = connect()
    try:
        pending_left = int(count_pending(conn).get("ready") or 0)
    finally:
        conn.close()
    return {
        "message": "started",
        "mode": "background",
        "selected": len(tids),
        "matched": 0,
        "requeued": 0,
        "crawled": 0,
        "imports": 0,
        "stubs": 0,
        "skipped": 0,
        "failed": 0,
        "pending_ready": pending_left,
        "items": [],
        "crawl": None,
        "note": (
            f"已在后台重爬选中的 {len(tids)} 条，进度见活动日志；"
            "单帖超时会跳过，避免整站卡死"
            + (f"；待抓队列仍有 {pending_left}" if pending_left else "")
        ),
    }


@router.post("/queue/retry-soft-ad")
async def post_retry_soft_ad(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """兼容旧接口：与异常重试相同。"""
    return await _post_queue_retry("abnormal")


@router.post("/recrawl-stubs")
async def post_recrawl_stubs(
    body: RecrawlStubsBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """用账号 Cookie 重爬焦点论坛优先占位；后台执行，进度见 status.account_stub_progress。"""
    from workers.recrawl import start_account_stub_recrawl

    body = body or RecrawlStubsBody()
    fid = _resolve_crawler_forum_id(body.forum_id)
    if fid not in FULL_CRAWLER_FORUM_IDS:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    _require_manual_idle(action="账号重爬")
    result = start_account_stub_recrawl(forum_id=fid)
    if not result.get("ok") and result.get("reason") in ("busy", "loop_running"):
        raise HTTPException(status_code=409, detail=str(result.get("error") or "爬虫正在处理其他任务，请稍候"))
    if not result.get("ok") and result.get("reason") == "no_account_cookie":
        raise HTTPException(status_code=400, detail=str(result.get("error") or "未配置账号 Cookie"))
    remaining = int(result.get("remaining") or result.get("budget") or 0)
    return {
        "message": "started" if result.get("started") else ("ok" if result.get("ok") else "failed"),
        "started": bool(result.get("started")),
        "forum_id": fid,
        "remaining": remaining,
        "budget": remaining,
        "stub_remaining": int(result.get("stub_remaining") or 0),
        "discarded_remaining": int(result.get("discarded_remaining") or 0),
        "result": result,
        "processed": 0,
        "upgraded": 0,
        "still_stub": 0,
        "failed": 0,
        "note": result.get("message") or result.get("error"),
    }


class AttachQueueRunBody(BaseModel):
    forum_id: str | None = None
    limit: int = Field(default=50, ge=1, le=50)


@router.get("/attach-queue/status")
def get_attach_queue_status(
    _user: dict = Depends(require_permission("crawler.view")),
) -> dict:
    from workers.attach_queue_runner import attach_queue_progress

    return {"message": "ok", **attach_queue_progress()}


@router.post("/attach-queue/run")
async def post_attach_queue_run(
    body: AttachQueueRunBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动排空附件日限队列（仅 2048；单日最多 50；再触日限即停）。"""
    from workers.attach_queue_runner import is_attach_queue_busy, run_attach_queue_once
    from workers.runner import crawl_status

    body = body or AttachQueueRunBody()
    if is_attach_queue_busy():
        raise HTTPException(status_code=409, detail="附件队列正在运行")
    st = crawl_status()
    if st.get("looping") or st.get("running"):
        raise HTTPException(status_code=409, detail="连续调度/爬虫运行中，请先停止再跑附件队列")
    _log_activity("手动触发附件队列排水")
    result = await run_attach_queue_once(
        forum_id=body.forum_id,
        limit=int(body.limit or 50),
        trigger="manual",
    )
    return {"message": "ok" if result.get("ok") else "failed", "result": result}
