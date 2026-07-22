"""爬虫活动页 API：状态 / 开关 / 一轮 / 连续调度（对齐拓扑）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth.deps import require_permission
from db.connection import connect
from db.forum_configs import (
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
    count_pending,
    count_pending_queue,
    list_discarded,
    list_discarded_reasons,
    list_pending_queue,
    list_pending_reasons,
    requeue_discarded_kind,
)
from workers.runner import (
    _log_activity,
    crawl_status,
    run_crawl_once,
    run_scan_head_once,
    start_continuous_loop,
    stop_continuous_loop,
    stop_crawler,
)
from workers.random_tid import run_random_tid_batch, start_random_tid_loop

router = APIRouter(prefix="/api/crawler", tags=["crawler"])


class EnabledBody(BaseModel):
    enabled: bool = True
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)


class RunBody(BaseModel):
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)
    persist: bool = True
    max_threads: int | None = Field(default=None, ge=1, le=500)
    scan_list: bool = True


class ScanHeadBody(BaseModel):
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)
    persist: bool = True
    max_pages: int | None = Field(default=None, ge=1, le=200)


class RandomTidBody(BaseModel):
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)
    persist: bool = True
    count: int | None = Field(default=None, ge=1, le=500, description="探测 tid 数上限")
    import_target: int | None = Field(
        default=None, ge=0, le=200, description="入库+占位目标；0=跑满本轮探测"
    )
    tid_min: int | None = Field(default=None, ge=1, le=50_000_000)
    tid_max: int | None = Field(default=None, ge=1, le=50_000_000)


class RandomTidLoopBody(BaseModel):
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)
    count: int | None = Field(default=200, ge=1, le=500, description="每轮随机探测数")
    tid_min: int | None = Field(default=None, ge=1, le=50_000_000)
    tid_max: int | None = Field(default=None, ge=1, le=50_000_000)


@router.get("/status")
def get_crawler_status(_user: dict = Depends(require_permission("crawler.view"))) -> dict:
    from parsers.boards import BOARD_POLICIES, enabled_queue_board_keys, queue_board_keys

    active = SITE_CRAWLER_FORUM_ID
    active_forum_name = SITE_CRAWLER_FORUM_ID
    cfg_forum_id = SITE_CRAWLER_FORUM_ID
    cfg: dict = {}
    board_fid = ""
    enabled_fids: list[str] = []
    qstats: dict = {}
    discarded_stats: dict = {}
    discarded_access_denied = 0
    discarded_failed_kind = 0
    active_ready = 0

    conn = connect()
    try:
        payload = build_forums_payload(conn)
        active = str(payload.get("active_forum_id") or get_active_forum_id(conn) or SITE_CRAWLER_FORUM_ID)
        forums = list(payload.get("forums") or [])
        active_forum = next((f for f in forums if str(f.get("id")) == active), None) or next(
            (f for f in forums if str(f.get("id")) == SITE_CRAWLER_FORUM_ID), None
        )
        active_forum_name = str((active_forum or {}).get("name") or active)
        configs = load_forum_configs_map(conn)
        # 状态面板跟随「当前选用论坛」；无专爬时回退站点专爬配置
        cfg_forum_id = active if active in configs else SITE_CRAWLER_FORUM_ID
        cfg = dict(configs.get(cfg_forum_id) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        board_fid = str(cfg.get("active_board_fid") or "")
        enabled_fids = resolve_enabled_board_fids(cfg)

        # 正常队列 = 启用子板全部待抓合计（实时），避免切板瞬间显示 0 却仍在入库
        queue_keys = enabled_queue_board_keys(enabled_fids)
        if not queue_keys and board_fid:
            queue_keys = queue_board_keys(board_fid)
        try:
            qstats = count_pending(conn, board_fid=queue_keys or None)
        except Exception:
            qstats = {}
        try:
            discarded_stats = count_discarded(conn, status="all")
        except Exception:
            discarded_stats = {}
        try:
            discarded_access_denied = count_discarded_kind(conn, "access_denied_bad_title")
        except Exception:
            discarded_access_denied = 0
        try:
            discarded_failed_kind = count_discarded_kind(conn, "failed_all")
        except Exception:
            discarded_failed_kind = 0
        if board_fid:
            try:
                active_ready = int(
                    count_pending(conn, board_fid=queue_board_keys(board_fid)).get("ready") or 0
                )
            except Exception:
                active_ready = 0
    finally:
        conn.close()

    priority_stubs = 0
    try:
        from db.repository import count_priority_account_stubs
        from db.resource_db import connect_resource

        rconn = connect_resource()
        try:
            priority_stubs = int(count_priority_account_stubs(rconn) or 0)
        finally:
            rconn.close()
    except Exception:
        priority_stubs = 0

    boards: list[dict] = []
    for efid in enabled_fids:
        if efid not in BOARD_POLICIES:
            continue
        pol = BOARD_POLICIES[efid]
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

    # 列表扫进行中：内存游标优先（每页已同步落库，这里再叠一层防读库延迟）
    board_cursors = dict(cfg.get("board_list_cursors") or {})
    if str(st.get("phase") or "") == "list_scan":
        for ck, pg in dict(st.get("board_list_cursors") or {}).items():
            try:
                board_cursors[str(ck)] = max(0, int(pg or 0))
            except (TypeError, ValueError):
                continue

    return {
        "forum_id": cfg_forum_id,
        "active_forum_id": active,
        "active_forum_name": active_forum_name,
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
        "board_list_cursors": board_cursors,
        "activity": st.get("activity") or [],
        "boards": boards,
        "queue": qstats or st.get("queue") or {},
        "discarded": discarded_stats or {},
        "throttle": st.get("throttle") or {},
        "metrics": {
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
            "discarded_access_denied_title": discarded_access_denied,
            "discarded_failed_kind": discarded_failed_kind,
            "account_pass_total": (
                int(priority_stubs) + int(discarded_access_denied) + int(discarded_failed_kind)
            ),
            "board_updated": last.get("board_updated") or 0,
        },
    }


@router.put("/enabled")
async def put_crawler_enabled(
    body: EnabledBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    fid = (body.forum_id or SITE_CRAWLER_FORUM_ID).strip()
    if fid != SITE_CRAWLER_FORUM_ID:
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
        _log_activity("论坛爬虫已开启")
        return {
            "message": "success",
            "forum_id": fid,
            "enabled": bool(saved.get("web_crawler_enabled")),
            "config": saved,
        }
    finally:
        conn.close()


@router.post("/run")
async def post_crawler_run(
    body: RunBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动立即爬取：只跑一轮；连续调度启用时不可触发。"""
    body = body or RunBody()
    fid = (body.forum_id or SITE_CRAWLER_FORUM_ID).strip()
    if fid != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail="连续调度进行中，请先关闭后再立即爬取")
    if st.get("running"):
        raise HTTPException(status_code=409, detail="上一轮仍在执行，请稍候")
    result = await run_crawl_once(
        forum_id=fid,
        persist=body.persist,
        max_threads=body.max_threads,
        scan_list=body.scan_list,
        scan_head=False,
        deep_scan=True,
        from_loop=False,
        require_enabled=False,
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "连续调度进行中"))
    return {"message": "ok" if result.get("ok") and not result.get("skipped") else "failed", "result": result}


@router.post("/scan-head")
async def post_crawler_scan_head(
    body: ScanHeadBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动扫新帖：首页捕新入队，本轮不做深扫；连续调度启用时不可触发。"""
    body = body or ScanHeadBody()
    fid = (body.forum_id or SITE_CRAWLER_FORUM_ID).strip()
    if fid != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail="连续调度进行中，请先关闭后再扫新帖")
    if st.get("running"):
        raise HTTPException(status_code=409, detail="上一轮仍在执行，请稍候")
    result = await run_scan_head_once(
        forum_id=fid,
        max_pages=body.max_pages,
        persist=body.persist,
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "连续调度进行中"))
    if result.get("reason") == "already_running":
        raise HTTPException(status_code=409, detail="上一轮仍在执行，请稍候")
    return {"message": "ok" if result.get("ok") and not result.get("skipped") else "failed", "result": result}


@router.post("/random-tid")
async def post_crawler_random_tid(
    body: RandomTidBody | None = None,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """手动随机抓帖：tid 直链探测早期帖，magnet+ed2k 混合判定入库。"""
    body = body or RandomTidBody()
    fid = (body.forum_id or SITE_CRAWLER_FORUM_ID).strip()
    if fid != SITE_CRAWLER_FORUM_ID:
        raise HTTPException(status_code=400, detail="该论坛尚未接入爬虫")
    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail="连续调度进行中，请先关闭后再随机抓帖")
    if st.get("running"):
        raise HTTPException(status_code=409, detail="上一轮仍在执行，请稍候")
    result = await run_random_tid_batch(
        forum_id=fid,
        probe=body.count,
        import_target=body.import_target,
        tid_min=body.tid_min,
        tid_max=body.tid_max,
        persist=body.persist,
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "连续调度进行中"))
    if result.get("reason") == "busy":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "爬虫正在执行"))
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
    fid = (body.forum_id or SITE_CRAWLER_FORUM_ID).strip()
    if fid != SITE_CRAWLER_FORUM_ID:
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
    """手动停止：协作退出 + 超时取消任务；关闭开关；队列任务不删除。"""
    result = await stop_crawler(disable=True, wait_seconds=12.0, force_after=8.0)
    return {
        "message": result.get("message") or "stopped",
        **result,
        "status": crawl_status(),
    }


async def _post_queue_retry(kind: str) -> dict:
    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail="连续调度进行中，请先关闭后再重试队列")
    if st.get("running"):
        raise HTTPException(status_code=409, detail="爬虫正在执行，请稍候")
    result = await run_crawl_once(
        persist=True,
        scan_list=False,
        from_loop=False,
        require_enabled=False,
        queue_kind=kind,
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "连续调度进行中"))
    return {
        "message": "ok" if result.get("ok") and not result.get("skipped") else "failed",
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
    """队列/占位明细分页：ready | abnormal | discarded | stubs。"""
    from parsers.boards import enabled_queue_board_keys, queue_board_keys

    key = (kind or "ready").strip().lower()
    if key not in {"ready", "abnormal", "discarded", "stubs"}:
        raise HTTPException(status_code=400, detail="kind 仅支持 ready / abnormal / discarded / stubs")
    lim = max(1, min(200, int(limit or 50)))
    off = max(0, int(offset or 0))
    query = (q or "").strip()
    reason_key = (reason or "").strip()

    if key == "discarded":
        st = (status or "all").strip().lower()
        if st not in {"all", "failed", "skipped"}:
            raise HTTPException(status_code=400, detail="status 仅支持 all / failed / skipped")
        conn = connect()
        try:
            counts = count_discarded(conn, status=st, q=query)
            total = (
                count_discarded(conn, status=st, q=query, reason=reason_key)["total"]
                if reason_key
                else int(counts.get("total") or 0)
            )
            items = list_discarded(
                conn, status=st, q=query, reason=reason_key or None, limit=lim, offset=off
            )
            reasons = list_discarded_reasons(conn, status=st, q=query)
            kind_counts = {
                k: count_discarded_kind(conn, k) for k in DISCARDED_REQUEUE_KINDS
            }
        finally:
            conn.close()
        return {
            "kind": key,
            "status": st,
            "q": query,
            "reason": reason_key,
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

        rconn = connect_resource()
        try:
            total = count_priority_account_stubs_q(
                rconn, q=query, reason=reason_key or None
            )
            items = list_priority_account_stubs(
                rconn, limit=lim, offset=off, q=query, reason=reason_key or None
            )
            reasons = list_priority_account_stub_reasons(rconn, q=query)
        finally:
            rconn.close()
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

    # ready / abnormal
    conn = connect()
    try:
        configs = load_forum_configs_map(conn)
        cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
        enabled_fids = resolve_enabled_board_fids(cfg)
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
    conn = connect()
    try:
        counts = count_discarded(conn, status=st, q=q)
        items = list_discarded(conn, status=st, q=q, limit=lim, offset=off)
        kind_counts = {
            key: count_discarded_kind(conn, key) for key in DISCARDED_REQUEUE_KINDS
        }
    finally:
        conn.close()
    return {
        "status": st,
        "q": (q or "").strip(),
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


class DiscardedRequeueBody(BaseModel):
    kind: str = Field(default="access_denied_bad_title")
    start_crawl: bool = True


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

    st = crawl_status()
    want_crawl = bool(body.start_crawl)
    crawl_blocked = want_crawl and bool(st.get("looping") or st.get("running"))

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

    crawl_result = None
    crawl_note = ""
    if want_crawl and requeued > 0 and not crawl_blocked:
        crawl_result = await run_crawl_once(
            persist=True,
            scan_list=False,
            from_loop=False,
            require_enabled=False,
        )
        if crawl_result.get("reason") == "loop_running":
            crawl_blocked = True
            crawl_result = None
    if crawl_blocked:
        crawl_note = "；爬虫忙，已入队待连续调度/空闲后抓取"

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
        "crawl": {
            "crawled": (crawl_result or {}).get("crawled") or 0,
            "imports": (crawl_result or {}).get("imports") or 0,
            "stubs": (crawl_result or {}).get("stubs") or 0,
            "skipped": (crawl_result or {}).get("skipped") or 0,
            "retries": (crawl_result or {}).get("retries") or 0,
            "failed": (crawl_result or {}).get("failed") or 0,
        }
        if crawl_result is not None
        else None,
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


@router.post("/queue/retry-soft-ad")
async def post_retry_soft_ad(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """兼容旧接口：与异常重试相同。"""
    return await _post_queue_retry("abnormal")


@router.post("/recrawl-stubs")
async def post_recrawl_stubs(
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """用账号 Cookie 重爬全部优先占位；后台执行，进度见 status.account_stub_progress。"""
    from workers.recrawl import start_account_stub_recrawl

    st = crawl_status()
    if st.get("looping"):
        raise HTTPException(status_code=409, detail="连续调度进行中，请先关闭后再账号爬占位")
    if st.get("running"):
        raise HTTPException(status_code=409, detail="上一轮仍在执行，请稍候")
    result = start_account_stub_recrawl()
    if not result.get("ok") and result.get("reason") in ("busy", "loop_running"):
        raise HTTPException(status_code=409, detail=str(result.get("error") or "爬虫正在执行"))
    if not result.get("ok") and result.get("reason") == "no_account_cookie":
        raise HTTPException(status_code=400, detail=str(result.get("error") or "未配置账号 Cookie"))
    remaining = int(result.get("remaining") or result.get("budget") or 0)
    return {
        "message": "started" if result.get("started") else ("ok" if result.get("ok") else "failed"),
        "started": bool(result.get("started")),
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
