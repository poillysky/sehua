"""FastAPI app — auth + ed2k-aligned persist + dual parse."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth.bootstrap import ensure_initial_admin, warn_if_no_users
from auth.deps import require_permission
from auth.middleware import AuthMiddleware
from auth.routes import router as auth_router
from api.forum_routes import router as forum_router
from api.settings_routes import router as settings_router
from api.crawler_routes import router as crawler_router
from api.import_routes import router as import_router
from api.backup_routes import router as backup_router
from auth.schema import ensure_auth_schema
from db.connection import connect, connection_mode, try_postgres
from db.forum_configs import SITE_CRAWLER_FORUM_ID, load_forum_configs_map, save_forum_config
from db.migrate import ensure_ed2k_schema
from db.persist import persist_from_html
from db.repository import (
    clear_forum_crawl_progress,
    delete_resource_by_hash,
    get_data_overview,
    list_recent_resources,
    list_resource_boards,
    list_resource_facets,
    list_resource_ids_for_selection,
    purge_crawl_data,
    purge_resources,
)
from db.resource_db import (
    connect_resource,
    open_resource_connection,
    resource_db_config,
    save_resource_db_config,
    test_resource_db_connection,
    using_separate_resource_db,
)
from parsers.links import parse_thread_dual

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        try_postgres().close()
        ensure_ed2k_schema()
        logger.info("ed2k schema aligned on Postgres")
    except Exception:
        logger.exception("ed2k schema migration failed — check POSTGRES_*")
        raise

    try:
        from db.migrate import run_migrations

        applied = run_migrations(only={"015_crawl_queue_retry.sql"})
        if applied:
            logger.info("queue migrations applied: %s", ", ".join(applied))
    except Exception:
        logger.exception("crawl queue migration failed")

    try:
        ensure_auth_schema()
        warn_if_no_users()
        ensure_initial_admin()
        logger.info("auth ready (%s)", connection_mode())
    except Exception:
        logger.exception("auth bootstrap failed")
        raise

    try:
        if using_separate_resource_db():
            # 独立资源库视为已有库：只连接读写，不自动跑迁移建表
            from db.resource_db import resource_dsn_kwargs

            dsn = resource_dsn_kwargs()
            logger.info(
                "resource DB separate · %s:%s/%s (no auto-migrate)",
                dsn.get("host"),
                dsn.get("port"),
                dsn.get("dbname"),
            )
    except Exception:
        logger.exception("resource DB config check failed — check 数据管理 → 资源数据库")
        raise

    from workers.backup import start_backup_scheduler, stop_backup_scheduler

    start_backup_scheduler()
    logger.info("resource backup scheduler started")
    try:
        from workers.runner import _log_activity, bind_main_loop, emergency_stop_sync
        from workers.emergency_stop_server import start_emergency_stop_server

        bind_main_loop()
        port = start_emergency_stop_server(emergency_stop_sync, port=18080)
        if port:
            logger.info("emergency stop ready on http://127.0.0.1:%s/stop", port)
        _log_activity("后端就绪 · 活动日志已落库，操作后可在此查看")
    except Exception:
        logger.debug("startup activity / emergency stop skipped", exc_info=True)
    try:
        yield
    finally:
        try:
            from workers.emergency_stop_server import stop_emergency_stop_server

            stop_emergency_stop_server()
        except Exception:
            pass
        await stop_backup_scheduler()


app = FastAPI(title="色花堂收集器 API", version="0.2.0", lifespan=lifespan)

def _cors_origins() -> list[str]:
    import os

    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://192.168.2.11:8081",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(forum_router)
app.include_router(settings_router)
app.include_router(crawler_router)
app.include_router(import_router)
app.include_router(backup_router)

_preview_dir = Path(__file__).resolve().parents[1] / "data" / "uploads" / "previews"
_preview_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static/previews", StaticFiles(directory=str(_preview_dir)), name="preview_uploads")


class ParseHtmlRequest(BaseModel):
    html: str
    tid: int = 0
    preferred_link: str = Field(default="both", pattern="^(magnet|ed2k|both)$")
    persist: bool = False
    source_url: str = ""
    board_fid: str = ""
    board_name: str = ""


@app.get("/health")
def health() -> dict:
    from db.connection import postgres_dsn_kwargs

    dsn = postgres_dsn_kwargs()
    db_ok = False
    db_error = ""
    try:
        conn = try_postgres()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        db_ok = True
    except Exception as exc:
        db_error = str(exc).split("\n")[0][:160]

    return {
        "status": "ok" if db_ok else "degraded",
        "db": {
            "ok": db_ok,
            "host": dsn["host"],
            "port": dsn["port"],
            "name": dsn["dbname"],
            "backend": connection_mode(),
            "error": db_error or None,
        },
        "schema": "ed2k",
    }


@app.get("/api/system/data-overview")
def data_overview(_user: dict = Depends(require_permission("settings.write"))) -> dict:
    from workers.runner import crawl_status

    conn = connect()
    rconn = None
    resource_db_error: str | None = None
    try:
        separate = using_separate_resource_db()
        if separate:
            rconn, resource_db_error = open_resource_connection()
            if rconn is None:
                # 独立库暂不可达：页面仍可打开，资源计数回落主库并带回错误提示
                separate = False
        overview = get_data_overview(conn, rconn if separate else None)
        configs = load_forum_configs_map(conn)
        cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
        st = crawl_status()
        return {
            "message": "success",
            "overview": overview,
            "crawler_running": bool(st.get("running") or st.get("looping")),
            "crawler_enabled": bool(cfg.get("web_crawler_enabled")),
            "resource_db": resource_db_config(mask_password=True),
            "resource_db_error": resource_db_error,
        }
    finally:
        if rconn is not None and rconn is not conn:
            try:
                rconn.close()
            except Exception:
                pass
        conn.close()


class ResourceDbBody(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int | None = None
    user: str = ""
    password: str | None = None
    dbname: str = ""
    keep_password: bool = True


@app.get("/api/system/resource-db")
def get_resource_db(_user: dict = Depends(require_permission("settings.write"))) -> dict:
    return {"message": "success", **resource_db_config(mask_password=True)}


@app.put("/api/system/resource-db")
def put_resource_db(
    body: ResourceDbBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    cfg = save_resource_db_config(
        enabled=bool(body.enabled),
        host=body.host or "",
        port=body.port,
        user=body.user or "",
        password=body.password,
        dbname=body.dbname or "",
        keep_password=bool(body.keep_password),
    )
    # 独立资源库只保存连接并用于读写；不自动建表/迁移。保存后探测连通性。
    connection_ok = True
    connection_error: str | None = None
    if cfg.get("enabled") and cfg.get("ready"):
        probe = test_resource_db_connection(
            enabled=True,
            host=str(cfg.get("host") or ""),
            port=cfg.get("port") if isinstance(cfg.get("port"), int) else body.port,
            user=str(cfg.get("user") or ""),
            password=body.password,
            dbname=str(cfg.get("dbname") or ""),
            use_saved_password=bool(body.keep_password) and not (body.password or "").strip(),
        )
        connection_ok = bool(probe.get("ok"))
        if not connection_ok:
            connection_error = str(probe.get("message") or "独立资源库连通失败")
    return {
        "message": "success",
        **cfg,
        "connection_ok": connection_ok,
        "connection_error": connection_error,
    }


@app.post("/api/system/resource-db/test")
def post_resource_db_test(
    body: ResourceDbBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    result = test_resource_db_connection(
        enabled=bool(body.enabled),
        host=body.host or "",
        port=body.port,
        user=body.user or "",
        password=body.password,
        dbname=body.dbname or "",
        use_saved_password=bool(body.keep_password) and not (body.password or "").strip(),
    )
    return {"message": "success", **result}


class SystemResetBody(BaseModel):
    confirm: str = ""


def _require_crawler_idle_or_409(*, disable_switch: bool = True) -> None:
    """爬虫运行中则请求停止并 409；可选关闭开关。"""
    from workers.runner import crawl_status, request_stop, stop_continuous_loop

    st = crawl_status()
    if st.get("running") or st.get("looping"):
        stop_continuous_loop()
        request_stop()
        if disable_switch:
            conn = connect()
            try:
                configs = load_forum_configs_map(conn)
                cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
                cfg["web_crawler_enabled"] = False
                save_forum_config(conn, SITE_CRAWLER_FORUM_ID, cfg)
            finally:
                conn.close()
        raise HTTPException(
            status_code=409,
            detail="爬虫正在执行中，已请求停止。请关闭爬虫并等待当前轮次结束后再试",
        )


def _disable_crawler_switch(conn) -> None:
    configs = load_forum_configs_map(conn)
    cfg = dict(configs.get(SITE_CRAWLER_FORUM_ID) or {})
    if cfg.get("web_crawler_enabled"):
        cfg["web_crawler_enabled"] = False
        save_forum_config(conn, SITE_CRAWLER_FORUM_ID, cfg)


@app.post("/api/system/reset")
def system_reset(
    body: SystemResetBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """清空资源 + 爬取记录（兼容旧接口）。"""
    if body.confirm.strip() != "清空":
        raise HTTPException(status_code=400, detail='请在确认框输入「清空」以继续')

    _require_crawler_idle_or_409(disable_switch=True)

    conn = connect()
    rconn = connect_resource()
    try:
        separate = using_separate_resource_db()
        before = get_data_overview(conn, rconn if separate else None)
        _disable_crawler_switch(conn)
        if separate:
            purge_resources(rconn, reset_crawl=False)
            purge_crawl_data(conn)
        else:
            purge_resources(conn, reset_crawl=True)
        clear_forum_crawl_progress(conn)
        return {
            "message": "success",
            "deleted": before,
            "crawler_enabled": False,
        }
    finally:
        rconn.close()
        conn.close()


@app.post("/api/system/reset-crawl")
def system_reset_crawl(
    body: SystemResetBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """只清空爬取记录（队列/进度/活动日志），保留资源库。"""
    if body.confirm.strip() != "清空爬取":
        raise HTTPException(status_code=400, detail='请在确认框输入「清空爬取」以继续')

    _require_crawler_idle_or_409(disable_switch=True)

    conn = connect()
    rconn = connect_resource()
    try:
        separate = using_separate_resource_db()
        before = get_data_overview(conn, rconn if separate else None)
        _disable_crawler_switch(conn)
        purge_crawl_data(conn)
        clear_forum_crawl_progress(conn)
        return {
            "message": "success",
            "scope": "crawl",
            "deleted": {
                "crawl_pages": before.get("crawl_pages") or 0,
                "crawl_pending": before.get("crawl_pending") or 0,
                "crawl_boards": before.get("crawl_boards") or 0,
                "activity_logs": before.get("activity_logs") or 0,
            },
            "crawler_enabled": False,
        }
    finally:
        rconn.close()
        conn.close()


@app.post("/api/system/reset-resources")
def system_reset_resources(
    body: SystemResetBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """只清空资源库，保留爬取队列与进度。"""
    if body.confirm.strip() != "清空资源":
        raise HTTPException(status_code=400, detail='请在确认框输入「清空资源」以继续')

    _require_crawler_idle_or_409(disable_switch=False)

    conn = connect()
    rconn = connect_resource()
    try:
        separate = using_separate_resource_db()
        before = get_data_overview(conn, rconn if separate else None)
        purge_resources(rconn, reset_crawl=False)
        return {
            "message": "success",
            "scope": "resources",
            "deleted": {
                "resources": before.get("resources") or 0,
                "resource_sources": before.get("resource_sources") or 0,
                "import_jobs": before.get("import_jobs") or 0,
            },
        }
    finally:
        rconn.close()
        conn.close()


@app.get("/api/resources/recent")
def resources_recent(
    page: int = 1,
    page_size: int = 30,
    limit: int | None = None,
    source: str = "",
    board: str = "",
    result: str = "",
    q: str = "",
) -> dict:
    """Paginated resources. Prefer page/page_size; legacy `limit` still accepted."""
    size = max(1, min(int(limit) if limit is not None else page_size, 100))
    page = max(1, page)
    offset = (page - 1) * size
    source_raw = source.strip()
    board_raw = board.strip()
    result_raw = result.strip()
    source_type = source_raw if source_raw and source_raw != "all" else None
    board_name = board_raw if board_raw and board_raw != "all" else None
    link_kind = result_raw if result_raw and result_raw != "all" else None
    query = q.strip() or None

    conn = connect_resource()
    try:
        items, total = list_recent_resources(
            conn,
            limit=size,
            offset=offset,
            source_type=source_type,
            board_name=board_name,
            link_kind=link_kind,
            q=query,
        )
        boards = list_resource_boards(conn)
        facets = list_resource_facets(
            conn,
            q=query,
            source_type=source_type,
            board_name=board_name,
            link_kind=link_kind,
        )
        # 兼容旧前端：boards 为名称列表；新前端用 facets.boards
        facet_board_names = [b["name"] for b in facets.get("boards") or [] if b.get("name")]
        pages = max(1, (total + size - 1) // size) if total else 1
        return {
            "items": items,
            "count": len(items),
            "total": total,
            "page": page,
            "page_size": size,
            "pages": pages,
            "boards": facet_board_names or boards,
            "facets": facets,
        }
    finally:
        conn.close()


@app.get("/api/resources/ids")
def resources_ids(
    source: str = "",
    board: str = "",
    result: str = "",
    q: str = "",
    limit: int = 2000,
) -> dict:
    """当前筛选条件下全部资源 id/hash（跨页全选）。"""
    source_raw = source.strip()
    board_raw = board.strip()
    result_raw = result.strip()
    source_type = source_raw if source_raw and source_raw != "all" else None
    board_name = board_raw if board_raw and board_raw != "all" else None
    link_kind = result_raw if result_raw and result_raw != "all" else None
    query = q.strip() or None
    lim = max(1, min(int(limit or 2000), 5000))

    conn = connect_resource()
    try:
        items, total = list_resource_ids_for_selection(
            conn,
            source_type=source_type,
            board_name=board_name,
            link_kind=link_kind,
            q=query,
            limit=lim,
        )
        return {
            "items": items,
            "count": len(items),
            "total": total,
            "limit": lim,
            "truncated": total > len(items),
            "ids": [int(it["id"]) for it in items if it.get("id") is not None],
            "hashes": [str(it["hash"]) for it in items if it.get("hash")],
        }
    finally:
        conn.close()


class RecrawlBody(BaseModel):
    hash: str = Field(..., min_length=8, max_length=128)


class RecrawlBatchBody(BaseModel):
    hashes: list[str] = Field(..., min_length=1, max_length=2000)


@app.post("/api/resources/delete")
def resources_delete(
    body: RecrawlBody,
    _user: dict = Depends(require_permission("resources.delete")),
) -> dict:
    """按 hash 删除单条资源（含来源与标签）。"""
    h = (body.hash or "").strip()
    if not h:
        raise HTTPException(status_code=400, detail="缺少 hash")
    conn = connect_resource()
    try:
        ok = delete_resource_by_hash(conn, h)
    finally:
        conn.close()
    if not ok:
        raise HTTPException(status_code=404, detail="资源不存在或已删除")
    return {"message": "ok", "hash": h, "deleted": True}


@app.post("/api/resources/delete-batch")
def resources_delete_batch(
    body: RecrawlBatchBody,
    _user: dict = Depends(require_permission("resources.delete")),
) -> dict:
    """按 hash 批量删除资源。"""
    hashes = []
    seen: set[str] = set()
    for raw in body.hashes:
        h = str(raw or "").strip()
        if len(h) < 8 or h in seen:
            continue
        seen.add(h)
        hashes.append(h)
    if not hashes:
        raise HTTPException(status_code=400, detail="缺少有效 hash")

    deleted = 0
    missing = 0
    conn = connect_resource()
    try:
        for h in hashes:
            if delete_resource_by_hash(conn, h):
                deleted += 1
            else:
                missing += 1
    finally:
        conn.close()
    return {
        "message": "ok",
        "deleted": deleted,
        "missing": missing,
        "requested": len(hashes),
    }


@app.post("/api/resources/recrawl")
async def resources_recrawl(
    body: RecrawlBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """已入库资源按来源帖重爬；同 hash upsert，不因标题产生重复。"""
    from workers.crawl_executor import await_crawl
    from workers.recrawl import recrawl_imported_resource

    result = await await_crawl(
        recrawl_imported_resource(body.hash),
        name="imported-recrawl-one",
    )
    if result.get("reason") in {"busy", "loop_running"} or result.get("skipped"):
        raise HTTPException(
            status_code=409,
            detail=str(result.get("error") or "爬虫忙，请稍后再试"),
        )
    if not result.get("ok") and not result.get("imported") and not result.get("removed"):
        detail = str(result.get("error") or result.get("verdict_label") or "重爬失败")
        raise HTTPException(status_code=400, detail=detail)
    return {"message": "ok", "result": result}


@app.post("/api/resources/recrawl-batch")
async def resources_recrawl_batch(
    body: RecrawlBatchBody,
    _user: dict = Depends(require_permission("crawl.run")),
) -> dict:
    """批量已入库重爬。

    连续调度中：同步入队后立即返回。
    空闲立即抓：爬虫线程后台执行，不堵 uvicorn 主循环。
    """
    from workers.crawl_executor import await_crawl, spawn_crawl
    from workers.recrawl import recrawl_imported_resources
    from workers.runner import _log_activity, crawl_status, recover_stuck_after_stop

    hashes = list(body.hashes or [])
    if len(hashes) > 2000:
        raise HTTPException(status_code=400, detail="一次最多重爬 2000 条")

    st = crawl_status()
    # 入队路径很快，可同步返回（也走爬虫线程，避免偶发堵主循环）
    if st.get("looping"):
        result = await await_crawl(
            recrawl_imported_resources(hashes),
            name="imported-recrawl-queue",
        )
        if result.get("reason") in {"busy", "loop_running"} or result.get("skipped"):
            raise HTTPException(
                status_code=409,
                detail=str(result.get("error") or "爬虫忙，请稍后再试"),
            )
        if (
            not result.get("ok")
            and int(result.get("imported") or 0) == 0
            and int(result.get("queued") or 0) == 0
            and int(result.get("removed") or 0) == 0
        ):
            raise HTTPException(
                status_code=400,
                detail=str(result.get("error") or "批量重爬失败"),
            )
        return {"message": "ok", "result": result}

    recover_stuck_after_stop(activity="已入库批量重爬")
    st = crawl_status()
    if st.get("running"):
        raise HTTPException(status_code=409, detail="爬虫正在执行，请稍后再重爬")

    cleaned: list[str] = []
    seen: set[str] = set()
    for h in hashes:
        key = (h or "").strip()
        if len(key) < 8 or key in seen:
            continue
        seen.add(key)
        cleaned.append(key)
    if not cleaned:
        raise HTTPException(status_code=400, detail="未提供有效 hash")

    _log_activity(f"已入库批量重爬 · 后台启动 {len(cleaned)} 条")

    async def _job() -> None:
        try:
            result = await recrawl_imported_resources(cleaned)
            if result.get("skipped") or result.get("reason") in {"busy", "loop_running"}:
                _log_activity(
                    f"已入库批量重爬未启动 · {result.get('error') or '爬虫忙'}"
                )
        except Exception as exc:
            logging.getLogger(__name__).exception("background imported recrawl")
            try:
                _log_activity(f"已入库批量重爬异常结束 · {exc}")
            except Exception:
                pass

    spawn_crawl(_job(), name="imported-recrawl-batch")
    return {
        "message": "ok",
        "result": {
            "ok": True,
            "mode": "background",
            "started": len(cleaned),
            "imported": 0,
            "queued": 0,
            "failed": 0,
            "note": (
                f"已在后台重爬 {len(cleaned)} 条，进度见爬虫活动日志；"
                "完成后会写「已入库批量重爬结束」。可用紧急停止中断。"
            ),
        },
    }


@app.post("/parse/thread")
def parse_thread(body: ParseHtmlRequest) -> dict:
    result = parse_thread_dual(
        body.html,
        tid=body.tid,
        preferred_link=body.preferred_link,  # type: ignore[arg-type]
    )
    payload: dict = {
        "tid": result.tid,
        "title": result.title,
        "primary_link_kind": result.primary_link_kind,
        "magnets": [
            {"hash": m.infohash, "filename": m.filename, "size": m.size, "uri": m.link}
            for m in result.magnets
        ],
        "ed2k_links": [
            {"hash": e.hash, "filename": e.filename, "size": e.size, "uri": e.link}
            for e in result.ed2k_links
        ],
        "assets": [
            {
                "link_kind": a.link_kind,
                "hash": a.hash,
                "filename": a.filename,
                "size": a.size,
                "uri": a.uri,
                "is_primary": a.is_primary,
            }
            for a in result.assets
        ],
        "metadata": result.metadata,
        "extract_password": result.extract_password,
        "preview_images": result.preview_images,
        "search_string": result.search_string,
    }

    if body.persist:
        url = (body.source_url or "").strip()
        if not url:
            raise HTTPException(status_code=400, detail="persist=true 时需要 source_url")
        conn = connect_resource()
        try:
            payload["persist"] = persist_from_html(
                conn,
                body.html,
                source_url=url,
                tid=body.tid,
                board_fid=body.board_fid,
                board_name=body.board_name,
                preferred_link=body.preferred_link,
            )
        finally:
            conn.close()

    return payload
