"""FastAPI app — auth + ed2k-aligned persist + dual parse."""

from __future__ import annotations

import logging
import os
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
    _count_multi_asset_threads,
    _ensure_resource_schema,
    _fast_thread_total,
    _resource_list_where,
    clear_forum_crawl_progress,
    clear_forum_head_catchup,
    delete_resource_by_hash,
    get_data_overview,
    list_recent_resources,
    list_resource_boards,
    list_resource_facets,
    list_resource_ids_for_selection,
    peek_cached_thread_total,
    peek_facet_thread_total,
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

_LOG_LEVEL_NAME = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
# 爬虫/worker 与 uvicorn 访问日志跟 LOG_LEVEL 对齐（DEBUG 时更细）
for _name in (
    "api",
    "crawler",
    "workers",
    "parsers",
    "db",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
):
    logging.getLogger(_name).setLevel(_LOG_LEVEL)
logger = logging.getLogger("api")
logger.info("logging ready level=%s", _LOG_LEVEL_NAME)


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
            # 独立资源库：空库补齐资源表；已有库只跑未应用的加性迁移
            from db.migrate import ensure_resource_db_schema
            from db.resource_db import connect_resource, resource_dsn_kwargs

            dsn = resource_dsn_kwargs()
            rconn = connect_resource()
            try:
                applied = ensure_resource_db_schema(rconn)
            finally:
                rconn.close()
            logger.info(
                "resource DB separate · %s:%s/%s%s",
                dsn.get("host"),
                dsn.get("port"),
                dsn.get("dbname"),
                f" · applied {', '.join(applied)}" if applied else " · schema up to date",
            )
        else:
            logger.info(
                "resource DB: using primary（未启用独立库；资源与元数据同机，仅建议单机）"
            )
    except Exception:
        # 独立库 migrate 失败：不拖垮启动，但健康检查会标 degraded；禁止假装写主库成功
        logger.exception(
            "resource DB config/migrate failed — 服务继续启动但资源写入可能不可用；"
            "请检查资源库或设置 RESOURCE_DB_* 环境变量"
        )

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
        # 进程启动：爬虫开关默认关闭（不自动恢复上次开启状态）
        try:
            from db.forum_configs import (
                FULL_CRAWLER_FORUM_IDS,
                load_forum_configs_map,
                save_forum_config,
            )

            conn = connect()
            try:
                configs = load_forum_configs_map(conn)
                cleared: list[str] = []
                for fid in FULL_CRAWLER_FORUM_IDS:
                    cfg = dict(configs.get(fid) or {})
                    if cfg.get("web_crawler_enabled"):
                        cfg["web_crawler_enabled"] = False
                        save_forum_config(conn, fid, cfg)
                        cleared.append(fid)
            finally:
                conn.close()
            if cleared:
                _log_activity(
                    f"后端启动 · 爬虫开关已重置为关闭（{', '.join(cleared)}）"
                )
            else:
                _log_activity("后端就绪 · 活动日志已落库，操作后可在此查看")
        except Exception:
            logger.debug("startup crawler disable skipped", exc_info=True)
            _log_activity("后端就绪 · 活动日志已落库，操作后可在此查看")
    except Exception:
        logger.debug("startup activity / emergency stop skipped", exc_info=True)
    try:
        # 预热进程池（spawn 首任务慢），避免首个大合集卡在冷启动
        try:
            from workers.cpu_pool import get_cpu_pool

            get_cpu_pool()
            logger.info("cpu process pool warmed")
        except Exception:
            logger.debug("cpu pool warm skipped", exc_info=True)
        # 预热处理记录侧面栏计数（冷查询数秒；不阻塞启动）
        try:
            import threading

            from db.repository import warm_resource_facets_cache

            threading.Thread(
                target=warm_resource_facets_cache,
                name="warm-resource-facets",
                daemon=True,
            ).start()
            logger.info("resource facets warm scheduled")
        except Exception:
            logger.debug("facets warm skipped", exc_info=True)
        yield
    finally:
        try:
            from workers.emergency_stop_server import stop_emergency_stop_server

            stop_emergency_stop_server()
        except Exception:
            pass
        try:
            from workers.cpu_pool import shutdown_cpu_pool

            shutdown_cpu_pool()
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
    from db.resource_db import (
        open_resource_connection,
        resource_db_config,
        settings_unavailable,
        using_separate_resource_db,
    )

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

    cfg = resource_db_config(mask_password=True)
    resource: dict = {
        "role": cfg.get("role") or "colocated_primary",
        "separate": False,
        "ok": True,
        "writable": True,
        "multi_terminal": False,
        "error": None,
        "architecture": cfg.get("architecture"),
    }
    try:
        if settings_unavailable():
            resource = {
                "role": "config_unavailable",
                "separate": True,
                "ok": False,
                "writable": False,
                "multi_terminal": True,
                "error": cfg.get("settings_error")
                or "无法读取资源库配置，已禁止写入以免写错库",
                "architecture": cfg.get("architecture"),
            }
        elif using_separate_resource_db():
            rconn, rerr = open_resource_connection()
            resource = {
                "role": "multi_terminal",
                "separate": True,
                "ok": rconn is not None,
                "writable": rconn is not None,
                "multi_terminal": True,
                "error": rerr,
                "config": cfg.get("effective"),
                "architecture": cfg.get("architecture"),
            }
            if rconn is not None:
                try:
                    rconn.close()
                except Exception:
                    pass
        else:
            resource["architecture"] = cfg.get("architecture")
    except Exception as exc:
        resource = {
            "role": "multi_terminal",
            "separate": True,
            "ok": False,
            "writable": False,
            "multi_terminal": True,
            "error": str(exc).split("\n")[0][:160],
        }

    status = "ok"
    if not db_ok:
        status = "degraded"
    elif not resource.get("ok") or not resource.get("writable", True):
        status = "degraded"

    return {
        "status": status,
        "db": {
            "ok": db_ok,
            "role": "metadata_self",
            "host": dsn["host"],
            "port": dsn["port"],
            "name": dsn["dbname"],
            "backend": connection_mode(),
            "error": db_error or None,
        },
        "resource_db": resource,
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
            if rconn is not None:
                overview = get_data_overview(conn, rconn)
            else:
                # 独立库启用但不可达：爬虫表仍可读主库；资源计数不回落主库
                overview = get_data_overview(conn, conn)
                overview["resources"] = None
                overview["resource_sources"] = None
                overview["import_jobs"] = None
                overview["sources"] = None
                overview["resource_db_separate"] = True
                overview["resource_db_unavailable"] = True
        else:
            overview = get_data_overview(conn, None)

        configs = load_forum_configs_map(conn)
        from db.forum_configs import get_active_forum_id

        active = get_active_forum_id(conn) or SITE_CRAWLER_FORUM_ID
        cfg = dict(configs.get(active) or configs.get(SITE_CRAWLER_FORUM_ID) or {})
        st = crawl_status()
        return {
            "message": "success",
            "overview": overview,
            "crawler_running": bool(st.get("running") or st.get("looping")),
            "crawler_enabled": bool(cfg.get("web_crawler_enabled")),
            "focus_forum_id": active,
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
                _disable_crawler_switch(conn)
            finally:
                conn.close()
        raise HTTPException(
            status_code=409,
            detail="爬虫正在执行中，已请求停止。请关闭爬虫并等待当前轮次结束后再试",
        )


def _disable_crawler_switch(conn) -> None:
    from db.forum_configs import get_active_forum_id

    configs = load_forum_configs_map(conn)
    active = get_active_forum_id(conn) or SITE_CRAWLER_FORUM_ID
    targets = {active, SITE_CRAWLER_FORUM_ID}
    for fid in targets:
        cfg = dict(configs.get(fid) or {})
        if cfg.get("web_crawler_enabled"):
            cfg["web_crawler_enabled"] = False
            save_forum_config(conn, fid, cfg)


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


@app.post("/api/system/reset-crawl-dates")
def system_reset_crawl_dates(
    body: SystemResetBody,
    _user: dict = Depends(require_permission("settings.write")),
) -> dict:
    """只清捕新日期闸门（board_head_catchup_on）与当日捕新进度，不动队列/深扫游标/资源。"""
    if body.confirm.strip() != "清理日期":
        raise HTTPException(status_code=400, detail='请在确认框输入「清理日期」以继续')

    _require_crawler_idle_or_409(disable_switch=False)

    conn = connect()
    try:
        cleared = clear_forum_head_catchup(conn)
        try:
            from workers.runner import _log_activity

            _log_activity(
                "已清理捕新日期闸门 · "
                f"论坛 {cleared.get('forums', 0)} · "
                f"日期项 {cleared.get('date_entries', 0)} · "
                f"进度项 {cleared.get('progress_entries', 0)}"
            )
        except Exception:
            pass
        return {
            "message": "success",
            "scope": "crawl_dates",
            "cleared": cleared,
        }
    finally:
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
    forum: str = "",
    q: str = "",
    include_facets: int = 1,
    include_total: int = 1,
    include_items: int = 1,
) -> dict:
    """Paginated resources. Prefer page/page_size; legacy `limit` still accepted.

    include_facets / include_total / include_items: 可拆请求——先出列表再补侧面栏。
    """
    size = max(1, min(int(limit) if limit is not None else page_size, 100))
    page = max(1, page)
    offset = (page - 1) * size
    source_raw = source.strip()
    board_raw = board.strip()
    result_raw = result.strip()
    forum_raw = forum.strip()
    source_type = source_raw if source_raw and source_raw != "all" else None
    board_name = board_raw if board_raw and board_raw != "all" else None
    link_kind = result_raw if result_raw and result_raw != "all" else None
    forum_id = forum_raw if forum_raw and forum_raw != "all" else None
    query = q.strip() or None
    want_facets = int(include_facets or 0) != 0
    want_total = int(include_total or 0) != 0
    want_items = int(include_items or 0) != 0
    has_filter = bool(
        (query or "").strip()
        or source_type
        or board_name
        or link_kind
        or forum_id
    )

    items: list = []
    total = None
    facets = None
    boards: list[str] | None = None

    # 无筛选的侧面栏/总数：先走内存/磁盘快照，不占资源库连接池
    # （后台全量预热曾占满池，导致处理记录「不加载」）
    # 注意：勿在本函数内再 `from db.repository import list_resource_facets`
    # （会把名字变成局部变量，有筛选分支触发 UnboundLocalError → 侧面栏 500）
    if not has_filter and not want_items:
        if want_facets:
            # conn=None：仅读快照/调度后台，不取池连接
            facets = list_resource_facets(
                None,
                q=query,
                source_type=source_type,
                board_name=board_name,
                link_kind=link_kind,
                forum_id=forum_id,
            )
            boards = [
                b["name"] for b in (facets.get("boards") or []) if b.get("name")
            ]
        if want_total:
            total = peek_cached_thread_total()
            if total is None and facets:
                try:
                    total = int((facets.get("results") or {}).get("all") or 0) or None
                except Exception:
                    total = None
        pages = (
            max(1, (int(total) + size - 1) // size)
            if want_total and total
            else None
        )
        return {
            "items": items,
            "count": 0,
            "total": total,
            "page": page,
            "page_size": size,
            "pages": pages,
            "boards": boards,
            "facets": facets,
        }

    # 单维筛选总数：优先侧面栏快照（毫秒），避免 capped GROUP BY 数秒
    if want_total and not want_items and has_filter:
        peeked_filter = peek_facet_thread_total(
            q=query,
            source_type=source_type,
            board_name=board_name,
            link_kind=link_kind,
            forum_id=forum_id,
        )
        if peeked_filter is not None:
            total = peeked_filter
            if want_facets:
                facets = list_resource_facets(
                    None,
                    q=query,
                    source_type=source_type,
                    board_name=board_name,
                    link_kind=link_kind,
                    forum_id=forum_id,
                )
                boards = [
                    b["name"] for b in (facets.get("boards") or []) if b.get("name")
                ]
            pages = max(1, (int(total) + size - 1) // size) if total else None
            return {
                "items": items,
                "count": 0,
                "total": total,
                "page": page,
                "page_size": size,
                "pages": pages,
                "boards": boards,
                "facets": facets,
            }

    # 仅侧面栏：无列表时优先快照/派生，不占资源库连接
    if want_facets and not want_items and not want_total:
        facets = list_resource_facets(
            None,
            q=query,
            source_type=source_type,
            board_name=board_name,
            link_kind=link_kind,
            forum_id=forum_id,
        )
        boards = [
            b["name"] for b in (facets.get("boards") or []) if b.get("name")
        ]
        return {
            "items": items,
            "count": 0,
            "total": None,
            "page": page,
            "page_size": size,
            "pages": None,
            "boards": boards,
            "facets": facets,
        }

    conn = connect_resource()
    try:
        if want_items:
            items, total = list_recent_resources(
                conn,
                limit=size,
                offset=offset,
                source_type=source_type,
                board_name=board_name,
                link_kind=link_kind,
                q=query,
                forum_id=forum_id,
                compute_total=want_total,
            )
        elif want_total:
            # 仅总数：不跑 oversample / 装配
            _ensure_resource_schema(conn)
            if (link_kind or "").strip() == "multi":
                peeked_multi = peek_facet_thread_total(
                    q=query,
                    source_type=source_type,
                    board_name=board_name,
                    link_kind=link_kind,
                    forum_id=forum_id,
                )
                if peeked_multi is not None:
                    total = peeked_multi
                else:
                    base_where, params = _resource_list_where(
                        source_type=source_type,
                        board_name=board_name,
                        link_kind=None,
                        q=query,
                        forum_id=forum_id,
                    )
                    with conn.cursor() as cur:
                        total = _count_multi_asset_threads(
                            cur, base_where, params, capped=True
                        )
            else:
                where_sql, params = _resource_list_where(
                    source_type=source_type,
                    board_name=board_name,
                    link_kind=link_kind,
                    q=query,
                    forum_id=forum_id,
                )
                if not has_filter:
                    peeked = peek_cached_thread_total()
                    if peeked is not None:
                        total = peeked
                    else:
                        with conn.cursor() as cur:
                            total = _fast_thread_total(
                                cur, where_sql, params, q=query, capped=False
                            )
                else:
                    peeked_filter = peek_facet_thread_total(
                        q=query,
                        source_type=source_type,
                        board_name=board_name,
                        link_kind=link_kind,
                        forum_id=forum_id,
                    )
                    if peeked_filter is not None:
                        total = peeked_filter
                    else:
                        with conn.cursor() as cur:
                            total = _fast_thread_total(
                                cur, where_sql, params, q=query, capped=True
                            )
        if want_facets:
            facets = list_resource_facets(
                conn,
                q=query,
                source_type=source_type,
                board_name=board_name,
                link_kind=link_kind,
                forum_id=forum_id,
            )
            facet_board_names = [
                b["name"] for b in facets.get("boards") or [] if b.get("name")
            ]
            boards = facet_board_names or list_resource_boards(conn)
        pages = (
            max(1, (int(total) + size - 1) // size)
            if want_total and total
            else None
        )
        return {
            "items": items,
            "count": len(items),
            "total": total,
            "page": page,
            "page_size": size,
            "pages": pages,
            "boards": boards,
            "facets": facets,
        }
    except Exception as exc:
        logger.exception("resources/recent failed")
        raise HTTPException(
            status_code=500,
            detail=(
                f"资源列表失败：{exc}。"
                "若启用了独立资源库，请确认目标库已建表（或先关闭独立资源库改回主库）。"
            ),
        ) from exc
    finally:
        conn.close()


@app.get("/api/resources/ids")
def resources_ids(
    source: str = "",
    board: str = "",
    result: str = "",
    forum: str = "",
    q: str = "",
    limit: int = 2000,
) -> dict:
    """当前筛选条件下全部资源 id/hash（跨页全选）。"""
    source_raw = source.strip()
    board_raw = board.strip()
    result_raw = result.strip()
    forum_raw = forum.strip()
    source_type = source_raw if source_raw and source_raw != "all" else None
    board_name = board_raw if board_raw and board_raw != "all" else None
    link_kind = result_raw if result_raw and result_raw != "all" else None
    forum_id = forum_raw if forum_raw and forum_raw != "all" else None
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
            forum_id=forum_id,
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
        reason = str(result.get("reason") or "")
        if reason == "loop_running":
            detail = "正在自动爬取中，请先到「爬虫」页点停止后再重爬"
        elif reason == "busy":
            detail = "爬虫正在处理其他任务，请稍等几秒再重爬"
        else:
            detail = str(result.get("error") or "系统正忙，请稍后再试")
        raise HTTPException(status_code=409, detail=detail)
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
            reason = str(result.get("reason") or "")
            if reason == "loop_running":
                detail = "正在自动爬取中，请先到「爬虫」页点停止后再重爬"
            elif reason == "busy":
                detail = "爬虫正在处理其他任务，请稍等几秒再重爬"
            else:
                detail = str(result.get("error") or "系统正忙，请稍后再试")
            raise HTTPException(status_code=409, detail=detail)
        if (
            not result.get("ok")
            and int(result.get("imported") or 0) == 0
            and int(result.get("queued") or 0) == 0
            and int(result.get("removed") or 0) == 0
        ):
            raise HTTPException(
                status_code=400,
                detail=str(result.get("error") or "批量重爬失败，请稍后重试"),
            )
        return {"message": "ok", "result": result}

    recover_stuck_after_stop(activity="已入库批量重爬")
    st = crawl_status()
    if st.get("running"):
        raise HTTPException(
            status_code=409,
            detail="爬虫正在处理其他任务，请稍等几秒再重爬",
        )

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
