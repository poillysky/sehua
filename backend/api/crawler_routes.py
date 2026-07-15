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
    save_forum_config,
)
from db.queue import count_pending
from workers.runner import (
    _log_activity,
    crawl_status,
    run_crawl_once,
    start_continuous_loop,
    stop_continuous_loop,
    stop_crawler,
)

router = APIRouter(prefix="/api/crawler", tags=["crawler"])


class EnabledBody(BaseModel):
    enabled: bool = True
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)


class RunBody(BaseModel):
    forum_id: str = Field(default=SITE_CRAWLER_FORUM_ID)
    persist: bool = True
    max_threads: int | None = Field(default=None, ge=1, le=500)
    scan_list: bool = True


@router.get("/status")
def get_crawler_status(_user: dict = Depends(require_permission("crawler.view"))) -> dict:
    from parsers.boards import BOARD_POLICIES

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
        try:
            qstats = count_pending(conn, board_fid=board_fid or None)
        except Exception:
            qstats = {}
    finally:
        conn.close()

    boards: list[dict] = []
    if board_fid.isdigit() and int(board_fid) in BOARD_POLICIES:
        pol = BOARD_POLICIES[int(board_fid)]
        boards = [
            {
                "fid": str(pol.fid),
                "name": pol.name,
                "pending": qstats.get("ready", "—"),
                "done": "—",
            }
        ]

    st = crawl_status()
    last = st.get("last_result") or {}
    return {
        "forum_id": cfg_forum_id,
        "active_forum_id": active,
        "active_forum_name": active_forum_name,
        "enabled": bool(cfg.get("web_crawler_enabled")),
        "active_board_fid": board_fid,
        "request_delay": cfg.get("web_crawler_request_delay"),
        "list_pages_per_board": cfg.get("web_crawler_list_pages_per_board"),
        "list_sort": "dateline",
        "list_sort_label": "按发帖时间",
        "interval_minutes": 0,
        "interval_label": "连续无间隔",
        "running": bool(st.get("running")),
        "looping": bool(st.get("looping")),
        "stopping": bool(st.get("stopping")),
        "phase": st.get("phase") or "idle",
        "last_started_at": st.get("last_started_at"),
        "last_finished_at": st.get("last_finished_at"),
        "last_result": last,
        "activity": st.get("activity") or [],
        "boards": boards,
        "queue": qstats or st.get("queue") or {},
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
            "queue_soft_ad": (qstats or {}).get("soft_ad") or 0,
            "queue_abnormal": (qstats or {}).get("abnormal") or 0,
            "queue_deferred": (qstats or {}).get("deferred") or 0,
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
        from_loop=False,
        require_enabled=False,
    )
    if result.get("reason") == "loop_running":
        raise HTTPException(status_code=409, detail=str(result.get("error") or "连续调度进行中"))
    return {"message": "ok" if result.get("ok") and not result.get("skipped") else "failed", "result": result}


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
    """在异常队列内重爬；成功（入库/占位/跳过/终态失败）才出队。"""
    return await _post_queue_retry("abnormal")


@router.post("/queue/retry-soft-ad")
async def post_retry_soft_ad(_user: dict = Depends(require_permission("crawl.run"))) -> dict:
    """在软文队列内重爬；成功才出队，失败仍留软文队列。"""
    return await _post_queue_retry("soft_ad")
